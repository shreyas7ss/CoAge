"""Durable student understanding check graph using LangGraph interrupt/resume."""

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.common.guardrails import sanitize_submission, wrap_untrusted
from app.agents.common.prompts import load_prompt
from app.schemas.llm import FollowupQuestionSet, FollowupScore


class FollowupState(TypedDict, total=False):
    followup_id: str
    questions: list[str]
    question_context: list[dict]
    original_answers: list[dict]
    references: list[dict]
    time_limit_sec: int
    student_answers: list[str]
    followup_score: dict


def build_followup_graph(checkpointer: Any = None, llm_factory: Any = None):
    from app.agents.common.llm import get_llm

    llm_factory = llm_factory or get_llm

    def generate_followup_questions(state: FollowupState) -> dict:
        if state.get("questions"):
            return {}
        template, _ = load_prompt("followup_questions")
        originals = [
            {
                "question_id": row.get("question_id"),
                "answer": wrap_untrusted(sanitize_submission(row.get("answer", ""))),
            }
            for row in state.get("original_answers", [])
        ]
        prompt = template.replace("[[CONTEXT]]", json.dumps(state.get("question_context", [])))
        prompt = prompt.replace("[[ANSWERS]]", json.dumps(originals))
        result = llm_factory().with_structured_output(FollowupQuestionSet).invoke(prompt)
        return {"questions": result.questions}

    def wait_for_student(state: FollowupState) -> dict:
        value = interrupt(
            {
                "followup_id": state["followup_id"],
                "questions": state.get("questions", []),
                "time_limit_sec": state.get("time_limit_sec", 420),
            }
        )
        answers = value.get("answers", []) if isinstance(value, dict) else []
        if len(answers) != len(state.get("questions", [])):
            raise ValueError("provide one answer for every follow-up question")
        return {"student_answers": [str(answer) for answer in answers]}

    def score_followup_answers(state: FollowupState) -> dict:
        template, _ = load_prompt("score_followup")
        originals = [
            {
                "question_id": row.get("question_id"),
                "answer": wrap_untrusted(sanitize_submission(row.get("answer", ""))),
            }
            for row in state.get("original_answers", [])
        ]
        followup = [
            {"question": question, "answer": wrap_untrusted(sanitize_submission(answer))}
            for question, answer in zip(
                state.get("questions", []), state.get("student_answers", []), strict=True
            )
        ]
        prompt = (
            template.replace(
                "[[CONTEXT]]",
                json.dumps(
                    {
                        "questions": state.get("question_context", []),
                        "reference_answers": state.get("references", []),
                    }
                ),
            )
            .replace("[[ORIGINAL]]", json.dumps(originals))
            .replace("[[FOLLOWUP]]", json.dumps(followup))
        )
        result = llm_factory().with_structured_output(FollowupScore).invoke(prompt)
        return {"followup_score": result.model_dump()}

    builder = StateGraph(FollowupState)
    builder.add_node("generate_followup_questions", generate_followup_questions)
    builder.add_node("wait_for_student", wait_for_student)
    builder.add_node("score_followup_answers", score_followup_answers)
    builder.add_edge(START, "generate_followup_questions")
    builder.add_edge("generate_followup_questions", "wait_for_student")
    builder.add_edge("wait_for_student", "score_followup_answers")
    builder.add_edge("score_followup_answers", END)
    return builder.compile(checkpointer=checkpointer)
