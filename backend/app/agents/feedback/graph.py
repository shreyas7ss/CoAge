"""Post-release feedback graph. It sees no authenticity records or other students."""

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.common.guardrails import sanitize_submission, wrap_untrusted
from app.agents.common.prompts import load_prompt
from app.schemas.llm import FeedbackGeneration


class FeedbackState(TypedDict, total=False):
    submission_id: str
    context: list[dict]
    results: list[dict]
    answers: list[dict]
    reference_answers: list[str]
    detected_misconceptions: list[str]
    weak_topics: list[str]
    generated: dict
    feedback: str
    misconceptions: list[str]
    suggested_practice: list[str]
    validation_errors: list[str]


def feedback_validation_errors(text: str, references: list[str]) -> list[str]:
    errors = []
    lowered = text.lower()
    if any(
        term in lowered
        for term in ("authenticity", "ai detector", "ai-generated", "other students")
    ):
        errors.append("feedback included prohibited context")
    for reference in references:
        normalized = reference.strip().casefold()
        if len(normalized) >= 12 and normalized in text.casefold():
            errors.append("feedback repeated a reference answer")
            break
    return errors


def build_feedback_graph(llm_factory: Any = None):
    from app.agents.common.llm import get_llm

    llm_factory = llm_factory or get_llm

    def detect_misconceptions(state: FeedbackState) -> dict:
        counts: dict[str, int] = {}
        for item in state.get("results", []):
            misconception = item.get("matched_misconception")
            if misconception:
                counts[misconception] = counts.get(misconception, 0) + 1
        ordered = [name for name, _count in sorted(counts.items(), key=lambda pair: -pair[1])]
        combined = list(dict.fromkeys(state.get("detected_misconceptions", []) + ordered))
        return {"detected_misconceptions": combined}

    def generate_feedback(state: FeedbackState) -> dict:
        template, _ = load_prompt("feedback_generate")
        answers = [
            {
                "question_id": row.get("question_id"),
                "answer": wrap_untrusted(sanitize_submission(row.get("answer", ""))),
            }
            for row in state.get("answers", [])
        ]
        prompt = (
            template.replace("[[CONTEXT]]", json.dumps(state.get("context", [])))
            .replace(
                "[[RESULTS]]",
                json.dumps(
                    {
                        "criteria": state.get("results", []),
                        "misconceptions": state.get("detected_misconceptions", []),
                        "weak_topics": state.get("weak_topics", []),
                    }
                ),
            )
            .replace("[[ANSWERS]]", json.dumps(answers))
        )
        output = llm_factory().with_structured_output(FeedbackGeneration).invoke(prompt)
        return {"generated": output.model_dump()}

    def validate_feedback(state: FeedbackState) -> dict:
        generated = state.get("generated", {})
        text = str(generated.get("feedback", ""))
        errors: list[str] = []
        errors.extend(feedback_validation_errors(text, state.get("reference_answers", [])))
        practices = list(generated.get("suggested_practice", []))
        if not 2 <= len(practices) <= 3:
            errors.append("feedback must include 2–3 practice prompts")
        if errors:
            weak_topics = state.get("weak_topics", [])
            fallback_topics = (weak_topics + ["assignment concepts", "your reasoning"])[:2]
            return {
                "validation_errors": errors,
                "feedback": (
                    "Review the feedback with your instructor. Revisit the topics listed below "
                    "and practice explaining your reasoning in your own words."
                ),
                "misconceptions": [],
                "suggested_practice": [
                    f"Explain one key idea from {topic} in your own words."
                    for topic in fallback_topics
                ],
            }
        return {
            "validation_errors": [],
            "feedback": text,
            "misconceptions": list(generated.get("misconceptions", [])),
            "suggested_practice": practices,
        }

    builder = StateGraph(FeedbackState)
    builder.add_node("detect_misconceptions", detect_misconceptions)
    builder.add_node("generate_feedback", generate_feedback)
    builder.add_node("validate_feedback", validate_feedback)
    builder.add_edge(START, "detect_misconceptions")
    builder.add_edge("detect_misconceptions", "generate_feedback")
    builder.add_edge("generate_feedback", "validate_feedback")
    builder.add_edge("validate_feedback", END)
    return builder.compile()
