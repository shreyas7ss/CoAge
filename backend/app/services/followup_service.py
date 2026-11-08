"""Persist and resume time-limited student understanding checks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.common import runner
from app.core.config import settings
from app.models.analytics import FollowupCheck
from app.models.assignment import Assignment, GradingPackage, Question
from app.models.submission import Submission, SubmissionAnswer
from app.services.authenticity_service import save_report


def _start_check(
    db: Session, check: FollowupCheck, submission: Submission, *, questions: list[str] | None = None
) -> dict:
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None:
        raise ValueError("assignment not found")
    question_rows = (
        db.query(Question).filter_by(assignment_id=assignment.id).order_by(Question.position).all()
    )
    answers = {
        str(answer.question_id): answer.answer_text
        for answer in db.query(SubmissionAnswer).filter_by(submission_id=submission.id).all()
    }
    package = (
        db.query(GradingPackage)
        .filter_by(assignment_id=assignment.id, version=assignment.active_package_version)
        .first()
    )
    package_questions = {
        row.get("q_id"): row
        for row in ((package.content or {}).get("questions", []) if package else [])
    }
    state = {
        "followup_id": str(check.id),
        "questions": questions or [],
        "question_context": [
            {"question_id": str(question.id), "question": question.prompt}
            for question in question_rows
        ],
        "original_answers": [
            {"question_id": qid, "answer": answer} for qid, answer in answers.items()
        ],
        "references": [
            {
                "question_id": qid,
                "reference_answer": package_questions[qid].get("reference_answer", ""),
            }
            for qid in answers
            if qid in package_questions
        ],
        "time_limit_sec": settings.followup_time_limit_sec,
    }
    thread_id = f"followup-{check.id}-{check.retake_count + 1}"
    result = runner.start("followup", thread_id, state)
    if result["status"] != "interrupted":
        raise RuntimeError("follow-up graph did not pause for student answers")
    payload = result["interrupt"][0]
    check.questions = payload["questions"]
    check.thread_id = thread_id
    check.time_limit_sec = int(payload["time_limit_sec"])
    check.issued_at = datetime.now(UTC)
    check.answered_at = None
    check.answers = None
    check.score = None
    db.flush()
    return {
        "status": "interrupted",
        "followup_id": str(check.id),
        "questions": check.questions,
        "time_limit_sec": check.time_limit_sec,
    }


def request_check(db: Session, submission: Submission) -> tuple[FollowupCheck, dict]:
    pending = (
        db.query(FollowupCheck)
        .filter(
            FollowupCheck.submission_id == submission.id,
            FollowupCheck.answered_at.is_(None),
        )
        .first()
    )
    if pending is not None:
        raise ValueError("an understanding check is already pending")
    check = FollowupCheck(
        submission_id=submission.id,
        questions=[],
        answers=None,
        score=None,
        time_limit_sec=settings.followup_time_limit_sec,
        retake_count=0,
        attempt_history=[],
    )
    db.add(check)
    db.flush()
    response = _start_check(db, check, submission)
    db.commit()
    return check, response


def submit_answers(
    db: Session, check: FollowupCheck, submission: Submission, answers: list[str]
) -> dict:
    if check.answered_at is not None:
        raise ValueError("this understanding check has already been answered")
    if len(answers) != len(check.questions):
        raise ValueError("provide one answer for every follow-up question")
    if check.issued_at is None or check.time_limit_sec is None:
        raise ValueError("follow-up check is not active")
    issued = (
        check.issued_at.replace(tzinfo=UTC) if check.issued_at.tzinfo is None else check.issued_at
    )
    if datetime.now(UTC) > issued + timedelta(seconds=check.time_limit_sec):
        raise ValueError("the follow-up answer window has expired")
    if not check.thread_id:
        raise ValueError("follow-up graph thread is missing")
    result = runner.resume("followup", check.thread_id, {"answers": answers})
    if result["status"] != "finished":
        raise RuntimeError("follow-up graph did not finish scoring")
    score = result["state"]["followup_score"]
    check.answers = answers
    check.score = float(score["score"])
    check.answered_at = datetime.now(UTC)
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None:
        raise ValueError("assignment not found")
    report = save_report(db, submission, assignment)
    db.commit()
    return {
        "status": "finished",
        "score": check.score,
        "reasoning": score["reasoning"],
        "authenticity_report_id": str(report.id),
    }


def retake_check(db: Session, check: FollowupCheck, submission: Submission) -> dict:
    if check.answered_at is None:
        raise ValueError("answer the current check before requesting a retake")
    if check.retake_count >= 1:
        raise ValueError("only one retake is allowed")
    history = list(check.attempt_history or [])
    history.append(
        {
            "questions": check.questions,
            "answers": check.answers,
            "score": float(check.score or 0),
            "answered_at": check.answered_at.isoformat(),
        }
    )
    check.attempt_history = history
    check.retake_count += 1
    response = _start_check(db, check, submission, questions=check.questions)
    db.commit()
    return response
