"""Authenticity reporting and optional process logging routes."""

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import (
    require_course_faculty,
    require_course_member,
    require_faculty,
    require_student,
)
from app.db.session import get_db
from app.models.analytics import FollowupCheck
from app.models.assignment import Assignment
from app.models.authenticity import AuthenticityReport, ProcessEvent
from app.models.course import Course
from app.models.submission import Submission
from app.models.user import User
from app.schemas.authenticity import (
    AuthenticityReportRead,
    AuthenticityReview,
    FollowupAnswers,
    FollowupRead,
    ProcessEventCreate,
    ProcessLoggingUpdate,
)
from app.services.authenticity_service import save_report, update_baseline_for_submission
from app.services.followup_service import request_check, retake_check, submit_answers

router = APIRouter(tags=["authenticity"])


def _owned_submission(db: Session, submission_id: uuid.UUID) -> tuple[Submission, Assignment]:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return submission, assignment


def _report(db: Session, submission: Submission, assignment: Assignment) -> AuthenticityReport:
    return save_report(db, submission, assignment)


@router.get("/submissions/{submission_id}/authenticity", response_model=AuthenticityReportRead)
def get_authenticity_report(
    submission_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> AuthenticityReport:
    submission, assignment = _owned_submission(db, submission_id)
    require_course_faculty(db, assignment.course_id, faculty)
    report = _report(db, submission, assignment)
    db.commit()
    return report


@router.post(
    "/submissions/{submission_id}/authenticity/request-check", status_code=status.HTTP_202_ACCEPTED
)
def request_understanding_check(
    submission_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    submission, assignment = _owned_submission(db, submission_id)
    require_course_faculty(db, assignment.course_id, faculty)
    try:
        _check, result = request_check(db, submission)
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return result


@router.post(
    "/submissions/{submission_id}/authenticity/review", response_model=AuthenticityReportRead
)
def review_authenticity_report(
    submission_id: uuid.UUID,
    payload: AuthenticityReview,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> AuthenticityReport:
    submission, assignment = _owned_submission(db, submission_id)
    require_course_faculty(db, assignment.course_id, faculty)
    report = _report(db, submission, assignment)
    report.reviewed = True
    report.faculty_note = (
        payload.note if payload.action == "note" else "Reviewed; no concern noted."
    )
    if payload.action == "no_concern":
        update_baseline_for_submission(db, submission, report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/courses/{course_id}/process-logging")
def set_process_logging(
    course_id: uuid.UUID,
    payload: ProcessLoggingUpdate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    course = require_course_faculty(db, course_id, faculty)
    course.process_logging_enabled = payload.enabled
    db.commit()
    return {"course_id": str(course.id), "enabled": course.process_logging_enabled}


@router.post("/submissions/{submission_id}/process-events", status_code=status.HTTP_201_CREATED)
def create_process_event(
    submission_id: uuid.UUID,
    payload: ProcessEventCreate,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    submission, assignment = _owned_submission(db, submission_id)
    if submission.student_id != student.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    require_course_member(db, assignment.course_id, student)
    course = db.get(Course, assignment.course_id)
    if course is None or not course.process_logging_enabled:
        raise HTTPException(
            status_code=409, detail="Process logging is not enabled for this course"
        )
    allowed = {"paste_size_pct", "active_seconds", "word_count", "draft_saves"}
    if set(payload.meta) - allowed or any(
        not math.isfinite(value) or value < 0 for value in payload.meta.values()
    ):
        raise HTTPException(
            status_code=422,
            detail="Only non-negative process counts and timing fields are accepted",
        )
    if "paste_size_pct" in payload.meta and payload.meta["paste_size_pct"] > 1:
        raise HTTPException(status_code=422, detail="paste_size_pct must be between 0 and 1")
    event = ProcessEvent(
        submission_id=submission.id, kind=payload.kind, count=payload.count, meta=payload.meta
    )
    db.add(event)
    save_report(db, submission, assignment)
    db.commit()
    return {"id": str(event.id), "status": "recorded"}


@router.get("/me/followups", response_model=list[FollowupRead])
def my_pending_followups(
    student: User = Depends(require_student), db: Session = Depends(get_db)
) -> list[FollowupCheck]:
    return list(
        db.query(FollowupCheck)
        .join(Submission, Submission.id == FollowupCheck.submission_id)
        .filter(Submission.student_id == student.id, FollowupCheck.answered_at.is_(None))
        .order_by(FollowupCheck.issued_at)
        .all()
    )


def _followup_for_student(
    db: Session, followup_id: uuid.UUID, student: User
) -> tuple[FollowupCheck, Submission]:
    check = db.get(FollowupCheck, followup_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    submission = db.get(Submission, check.submission_id)
    if submission is None or submission.student_id != student.id:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return check, submission


@router.post("/followups/{followup_id}/answers", status_code=status.HTTP_202_ACCEPTED)
def answer_followup(
    followup_id: uuid.UUID,
    payload: FollowupAnswers,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    check, submission = _followup_for_student(db, followup_id, student)
    try:
        return submit_answers(db, check, submission, payload.answers)
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.post("/followups/{followup_id}/retake", status_code=status.HTTP_202_ACCEPTED)
def retake_followup(
    followup_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    check, submission = _followup_for_student(db, followup_id, student)
    try:
        return retake_check(db, check, submission)
    except ValueError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
