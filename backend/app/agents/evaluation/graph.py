"""Graph B: Submission Evaluation Graph (the core).

Flow (see docs/04-LANGGRAPH-AGENTS.md §2):
    load -> injection_check -> route (Send fan-out: mcq -> deterministic_grader,
    text -> score_criterion per criterion) -> aggregate_scores -> confidence_gate
    -> draft_feedback_for_reviewer -> faculty_review (interrupt) -> finalize.

The graph is *pure* (no DB access). The service loads the submission/package into
the input state and persists the mirrored results after interrupt/finalize.
"""

import json
import operator
import statistics
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from app.agents.common.guardrails import detect_injection, sanitize_submission, wrap_untrusted
from app.agents.common.prompts import load_prompt
from app.agents.common.scoring import grade_mcq, score_with_self_consistency
from app.core.config import settings
from app.schemas.llm import CriterionResult, FeedbackDraft


class EvalState(TypedDict, total=False):
    submission_id: str
    assignment_id: str
    package_version: int
    answers: dict[str, str]  # q_id -> student answer text
    question: dict[str, Any]
    criterion: dict[str, Any]
    answer: str
    questions: list[dict]  # [{q_id, prompt, qtype, max_marks, mcq_* , test_cases}]
    package: dict  # approved grading package content
    criteria_by_qid: dict[str, list[dict]]  # q_id -> [{criterion_id, description, marks, topic_id}]
    late_penalty_pct: float
    criterion_scores: Annotated[list[dict], operator.add]
    question_totals: dict[str, float]
    topic_scores: dict[str, float]
    ai_total: float
    overall_confidence: float
    flags: dict
    injection_flags: list[dict]
    feedback_draft: dict
    faculty_decision: dict | None
    final_criterion_scores: list[dict]
    final_total: float
    approved: bool


def _package_lookup(package: dict) -> dict:
    return {q.get("q_id"): q for q in package.get("questions", [])}


def _render_score_prompt(
    template: str, question: dict, criterion: dict, answer: str, pkg: dict
) -> str:
    return (
        template.replace("[[QUESTION]]", question.get("prompt", ""))
        .replace("[[REFERENCE]]", pkg.get("reference_answer", ""))
        .replace("[[ALTERNATIVES]]", pkg.get("acceptable_alternatives", ""))
        .replace("[[CRITERION]]", criterion.get("description", ""))
        .replace("[[MAX_MARKS]]", str(criterion.get("marks", "")))
        .replace("[[MISCONCEPTIONS]]", json.dumps(pkg.get("common_misconceptions", [])))
        .replace("[[ANSWER]]", wrap_untrusted(answer))
    )


def build_evaluation_graph(checkpointer: Any = None, llm_factory: Any = None):
    from app.agents.common.llm import get_llm

    llm_factory = llm_factory or get_llm

    def load_submission_and_package(state: EvalState) -> dict:
        answers = dict(state.get("answers") or {})
        for question in state.get("questions", []):
            answers.setdefault(question["q_id"], "")
        return {"answers": answers}

    def injection_check(state: EvalState) -> dict:
        flags = []
        for q_id, text in state.get("answers", {}).items():
            markers = detect_injection(text)
            if markers:
                flags.append({"q_id": q_id, "markers": markers})
        return {"injection_flags": flags}

    def route_questions(state: EvalState) -> Any:
        sends: list[Send] = []
        package = state.get("package", {})
        criteria_by_qid = state.get("criteria_by_qid", {})
        for question in state.get("questions", []):
            q_id = question["q_id"]
            answer = state.get("answers", {}).get(q_id, "")
            if question.get("qtype") == "mcq":
                criterion = (criteria_by_qid.get(q_id) or [{}])[0]
                sends.append(
                    Send(
                        "deterministic_grader",
                        {"question": question, "criterion": criterion, "answer": answer},
                    )
                )
            else:
                for criterion in criteria_by_qid.get(q_id, []):
                    sends.append(
                        Send(
                            "score_criterion",
                            {
                                "question": question,
                                "criterion": criterion,
                                "answer": answer,
                                "package": package,
                            },
                        )
                    )
        return sends if sends else "aggregate_scores"

    def deterministic_grader(state: EvalState) -> dict:
        question = state.get("question", {})
        criterion = state.get("criterion", {})
        answer = state.get("answer", "")
        max_marks = float(criterion.get("marks") or question.get("max_marks") or 0)
        result = grade_mcq(
            answer, question.get("mcq_correct"), question.get("mcq_options"), max_marks
        )
        return {
            "criterion_scores": [
                {
                    "criterion_id": criterion.get("criterion_id"),
                    "q_id": question.get("q_id"),
                    "topic_id": criterion.get("topic_id"),
                    "ai_awarded": result["ai_awarded"],
                    "max_marks": max_marks,
                    "evidence": result["evidence"],
                    "matched_misconception": result["matched_misconception"],
                    "confidence": result["confidence"],
                    "needs_manual": result["needs_manual"],
                }
            ]
        }

    def score_criterion(state: EvalState) -> dict:
        question = state["question"]
        criterion = state["criterion"]
        answer = state.get("answer", "")
        max_marks = float(criterion.get("marks") or question.get("max_marks") or 0)
        pkg = _package_lookup(state.get("package", {})).get(question.get("q_id"), {})
        structured = llm_factory().with_structured_output(CriterionResult)
        template, _ = load_prompt("score_criterion")
        prompt = _render_score_prompt(
            template, question, criterion, sanitize_submission(answer), pkg
        )
        result = score_with_self_consistency(structured, prompt, max_marks)
        return {
            "criterion_scores": [
                {
                    "criterion_id": criterion.get("criterion_id"),
                    "q_id": question.get("q_id"),
                    "topic_id": criterion.get("topic_id"),
                    "ai_awarded": result["ai_awarded"],
                    "max_marks": max_marks,
                    "evidence": result["evidence"],
                    "matched_misconception": result["matched_misconception"],
                    "confidence": result["confidence"],
                    "needs_manual": result["needs_manual"],
                }
            ]
        }

    def aggregate_scores(state: EvalState) -> dict:
        totals: dict[str, float] = {}
        for score in state.get("criterion_scores", []):
            q_id = score["q_id"]
            totals[q_id] = round(totals.get(q_id, 0.0) + float(score["ai_awarded"]), 2)
        return {"question_totals": totals, "ai_total": round(sum(totals.values()), 2)}

    def confidence_gate(state: EvalState) -> dict:
        scores = state.get("criterion_scores", [])
        confidences = [float(s["confidence"]) for s in scores if s.get("confidence") is not None]
        overall = statistics.mean(confidences) if confidences else 0.0
        flags = {
            "low_confidence": overall < settings.confidence_review_threshold,
            "needs_manual": any(s.get("needs_manual") for s in scores),
            "injection": bool(state.get("injection_flags")),
        }
        return {"overall_confidence": round(overall, 4), "flags": flags}

    def compute_topic_scores(state: EvalState) -> dict:
        awarded: dict[str, float] = {}
        possible: dict[str, float] = {}
        for score in state.get("criterion_scores", []):
            topic_id = score.get("topic_id")
            if not topic_id:
                continue
            awarded[topic_id] = awarded.get(topic_id, 0.0) + float(score["ai_awarded"])
            possible[topic_id] = possible.get(topic_id, 0.0) + float(score["max_marks"])
        return {
            "topic_scores": {
                topic_id: round(awarded[topic_id] / marks, 4) if marks > 0 else 0.0
                for topic_id, marks in possible.items()
            }
        }

    def draft_feedback_for_reviewer(state: EvalState) -> dict:
        structured = llm_factory().with_structured_output(FeedbackDraft)
        template, _ = load_prompt("feedback_draft")
        prompt = (
            template.replace("[[AI_TOTAL]]", str(state.get("ai_total", 0)))
            .replace("[[CONFIDENCE]]", str(state.get("overall_confidence", 0)))
            .replace("[[SCORES]]", json.dumps(state.get("criterion_scores", [])))
        )
        result = structured.invoke(prompt)
        return {"feedback_draft": result.model_dump()}

    def faculty_review(state: EvalState) -> dict:
        decision = interrupt(
            {
                "submission_id": state["submission_id"],
                "ai_total": state.get("ai_total"),
                "criterion_scores": state.get("criterion_scores", []),
                "topic_scores": state.get("topic_scores", {}),
                "feedback_draft": state.get("feedback_draft"),
                "overall_confidence": state.get("overall_confidence"),
                "flags": state.get("flags", {}),
                "injection_flags": state.get("injection_flags", []),
            }
        )
        return {"faculty_decision": decision}

    def finalize(state: EvalState) -> dict:
        decision = state.get("faculty_decision") or {}
        approve = bool(decision.get("approve", True))
        final_scores = decision.get("final_scores") or {}
        entries: list[dict] = []
        total = 0.0
        for score in state.get("criterion_scores", []):
            key = score.get("criterion_id") or f"mcq:{score.get('q_id')}"
            final = float(final_scores.get(key, score.get("ai_awarded", 0.0)))
            if not 0 <= final <= float(score.get("max_marks", 0.0)):
                raise ValueError(f"final score for {key} must be within [0, max_marks]")
            entries.append({**score, "final_awarded": final})
            total += final
        penalty = float(state.get("late_penalty_pct") or 0.0)
        if not 0 <= penalty <= 100:
            raise ValueError("late_penalty_pct must be within [0, 100]")
        if penalty > 0:
            total = round(total * (1 - penalty / 100.0), 2)
        return {"final_criterion_scores": entries, "final_total": total, "approved": approve}

    builder = StateGraph(EvalState)
    builder.add_node("load_submission_and_package", load_submission_and_package)
    builder.add_node("injection_check", injection_check)
    builder.add_node("deterministic_grader", deterministic_grader)
    builder.add_node("score_criterion", score_criterion)
    builder.add_node("aggregate_scores", aggregate_scores)
    builder.add_node("compute_topic_scores", compute_topic_scores)
    builder.add_node("confidence_gate", confidence_gate)
    builder.add_node("draft_feedback_for_reviewer", draft_feedback_for_reviewer)
    builder.add_node("faculty_review", faculty_review)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "load_submission_and_package")
    builder.add_edge("load_submission_and_package", "injection_check")
    builder.add_conditional_edges(
        "injection_check",
        route_questions,
        ["deterministic_grader", "score_criterion", "aggregate_scores"],
    )
    builder.add_edge("deterministic_grader", "aggregate_scores")
    builder.add_edge("score_criterion", "aggregate_scores")
    builder.add_edge("aggregate_scores", "compute_topic_scores")
    builder.add_edge("compute_topic_scores", "confidence_gate")
    builder.add_edge("confidence_gate", "draft_feedback_for_reviewer")
    builder.add_edge("draft_feedback_for_reviewer", "faculty_review")
    builder.add_edge("faculty_review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
