"""Submission evaluation service: orchestrate the evaluation graph and mirror results."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.common import runner
from app.agents.common.prompts import load_prompt
from app.analytics.service import write_mastery_events
from app.core.config import settings
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.enums import EvalStatus, SubmissionStatus
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer


def build_input_state(db: Session, submission: Submission, assignment: Assignment) -> dict:
    questions = (
        db.query(Question)
        .filter(Question.assignment_id == assignment.id)
        .order_by(Question.position)
        .all()
    )
    package = (
        db.query(GradingPackage)
        .filter_by(assignment_id=assignment.id, version=assignment.active_package_version)
        .first()
    )
    criteria = (
        db.query(RubricCriterion)
        .join(Question, Question.id == RubricCriterion.question_id)
        .filter(
            Question.assignment_id == assignment.id,
            RubricCriterion.package_version == assignment.active_package_version,
        )
        .all()
    )
    answers = {
        str(a.question_id): a.answer_text
        for a in db.query(SubmissionAnswer)
        .filter(SubmissionAnswer.submission_id == submission.id)
        .all()
    }

    criteria_by_qid: dict[str, list[dict]] = {}
    for rc in criteria:
        criteria_by_qid.setdefault(str(rc.question_id), []).append(
            {
                "criterion_id": str(rc.id),
                "description": rc.description,
                "marks": float(rc.marks),
                "topic_id": str(rc.topic_id) if rc.topic_id else None,
            }
        )

    late_penalty = float(assignment.late_penalty_pct or 0) if submission.is_late else 0.0
    return {
        "submission_id": str(submission.id),
        "assignment_id": str(assignment.id),
        "package_version": assignment.active_package_version,
        "answers": answers,
        "questions": [
            {
                "q_id": str(q.id),
                "prompt": q.prompt,
                "qtype": q.qtype.value,
                "max_marks": float(q.max_marks),
                "mcq_correct": q.mcq_correct,
                "mcq_options": q.mcq_options,
                "test_cases": q.test_cases,
            }
            for q in questions
        ],
        "package": package.content if package else {"questions": []},
        "criteria_by_qid": criteria_by_qid,
        "late_penalty_pct": late_penalty,
        "criterion_scores": [],
        "injection_flags": [],
    }


def run_evaluation(db: Session, submission: Submission) -> dict:
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None or assignment.active_package_version is None:
        submission.status = SubmissionStatus.needs_attention
        db.commit()
        return {"status": "error", "detail": "no approved grading package"}

    state = build_input_state(db, submission, assignment)
    evaluation = Evaluation(
        submission_id=submission.id,
        package_version=assignment.active_package_version,
        model=settings.llm_model or None,
        prompt_version=load_prompt("score_criterion")[1][:8],
        status=EvalStatus.running,
    )
    db.add(evaluation)
    db.flush()
    thread_id = f"eval-{submission.id}"
    submission.eval_thread_id = thread_id
    submission.status = SubmissionStatus.under_evaluation
    db.commit()

    result = runner.start("evaluation", thread_id, state)
    if result["status"] == "interrupted":
        _mirror_interrupt(db, evaluation, submission, result["interrupt"][0])
    else:
        _finalize_finished(db, evaluation, submission, result["state"], approved=False)
    db.commit()
    return result


def resume_evaluation(
    db: Session, evaluation: Evaluation, decision: dict, reviewer_id: uuid.UUID
) -> dict:
    submission = db.get(Submission, evaluation.submission_id)
    if submission is None or submission.eval_thread_id is None:
        raise ValueError("submission evaluation thread not found")
    result = runner.resume("evaluation", submission.eval_thread_id, decision)
    if result["status"] == "finished":
        _finalize_finished(
            db,
            evaluation,
            submission,
            result["state"],
            approved=result["state"].get("approved", True),
            reviewer_id=reviewer_id,
        )
    db.commit()
    return result


def _mirror_interrupt(
    db: Session, evaluation: Evaluation, submission: Submission, payload: dict
) -> None:
    evaluation.status = EvalStatus.awaiting_review
    evaluation.ai_total = payload.get("ai_total")
    evaluation.confidence = payload.get("overall_confidence")
    submission.status = SubmissionStatus.pending_review
    for score in payload.get("criterion_scores", []):
        criterion_id = score.get("criterion_id")
        db.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                criterion_id=uuid.UUID(criterion_id) if criterion_id else None,
                ai_awarded=score.get("ai_awarded"),
                max_marks=score.get("max_marks"),
                evidence=score.get("evidence"),
                matched_misconception=score.get("matched_misconception"),
                confidence=score.get("confidence"),
                needs_manual=bool(score.get("needs_manual", False)),
            )
        )


def _finalize_finished(
    db: Session,
    evaluation: Evaluation,
    submission: Submission,
    state: dict,
    *,
    approved: bool,
    reviewer_id: uuid.UUID | None = None,
) -> None:
    evaluation.final_total = state.get("final_total")
    evaluation.reviewed_by = reviewer_id
    evaluation.reviewed_at = datetime.now(UTC)
    evaluation.status = EvalStatus.approved if approved else EvalStatus.rejected
    submission.status = SubmissionStatus.graded if approved else SubmissionStatus.needs_attention

    final_by_criterion = {
        str(s["criterion_id"]): s["final_awarded"]
        for s in state.get("final_criterion_scores", [])
        if s.get("criterion_id")
    }
    for score in (
        db.query(CriterionScore).filter(CriterionScore.evaluation_id == evaluation.id).all()
    ):
        key = str(score.criterion_id) if score.criterion_id else None
        if key in final_by_criterion:
            score.final_awarded = final_by_criterion[key]
    if approved:
        write_mastery_events(db, submission, evaluation)
