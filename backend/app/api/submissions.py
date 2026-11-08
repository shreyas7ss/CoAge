"""Submissions, review queue, and evaluation decision router."""

import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.deps import (
    require_course_faculty,
    require_course_member,
    require_faculty,
    require_student,
)
from app.db.session import get_db
from app.models.assignment import Assignment, Question
from app.models.enums import EvalStatus, SubmissionStatus
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer
from app.models.user import User
from app.schemas.submission import (
    CriterionScoreRead,
    EvaluationDecision,
    EvaluationDetail,
    EvaluationRead,
    SubmissionRead,
    SubmissionResultRead,
)
from app.services import evaluation_service
from app.services.parsing import (
    extract_text_from_docx,
    extract_text_from_pdf,
    parse_submission_answers,
)

router = APIRouter(tags=["submissions"])


def _get_assignment_or_404(db: Session, assignment_id: uuid.UUID) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment


def _get_evaluation_or_404(db: Session, evaluation_id: uuid.UUID) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    return evaluation


def _require_evaluation_faculty(
    db: Session, evaluation: Evaluation, faculty: User
) -> tuple[Submission, Assignment]:
    submission = db.get(Submission, evaluation.submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    require_course_faculty(db, assignment.course_id, faculty)
    return submission, assignment


@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    assignment_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    ai_disclosure: str | None = Form(None),
) -> Submission:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_member(db, assignment.course_id, student)
    if assignment.status != "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Assignment is not published"
        )
    if assignment.active_package_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assignment has no approved grading package",
        )

    content = ""
    if file is not None:
        data = await file.read()
        filename = (file.filename or "").lower()
        if filename.endswith(".pdf"):
            content = extract_text_from_pdf(data)
        elif filename.endswith(".docx"):
            content = extract_text_from_docx(data)
        else:
            content = data.decode("utf-8", errors="replace")
    if text:
        content = content + ("\n" + text if content else text)
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No submission content provided",
        )

    questions = (
        db.query(Question)
        .filter(Question.assignment_id == assignment_id)
        .order_by(Question.position)
        .all()
    )
    answers = parse_submission_answers(
        content, [{"q_id": str(q.id), "position": q.position} for q in questions]
    )

    now = datetime.now(UTC)
    deadline = assignment.deadline
    if deadline.tzinfo is None:  # SQLite stores naive datetimes; assume UTC
        deadline = deadline.replace(tzinfo=UTC)
    is_late = now > deadline
    submission = (
        db.query(Submission).filter_by(assignment_id=assignment_id, student_id=student.id).first()
    )
    if submission is None:
        submission = Submission(
            assignment_id=assignment_id,
            student_id=student.id,
            submitted_at=now,
            is_late=is_late,
            status=SubmissionStatus.submitted,
            ai_disclosure=ai_disclosure,
        )
        db.add(submission)
        db.flush()
    else:
        submission.submitted_at = now
        submission.is_late = is_late
        submission.ai_disclosure = ai_disclosure
        submission.status = SubmissionStatus.submitted
        db.query(SubmissionAnswer).filter(SubmissionAnswer.submission_id == submission.id).delete()

    for question in questions:
        db.add(
            SubmissionAnswer(
                submission_id=submission.id,
                question_id=question.id,
                answer_text=answers.get(str(question.id), ""),
            )
        )
    db.commit()

    # Persist first, then let FastAPI run the evaluation after sending the response.
    # The database dependency remains alive through response background tasks.
    background_tasks.add_task(evaluation_service.run_evaluation, db, submission)
    return submission


@router.get("/assignments/{assignment_id}/my-submission", response_model=SubmissionRead)
def my_submission(
    assignment_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> Submission:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_member(db, assignment.course_id, student)
    submission = (
        db.query(Submission).filter_by(assignment_id=assignment_id, student_id=student.id).first()
    )
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No submission yet")
    return submission


@router.get("/me/submissions", response_model=list[SubmissionRead])
def my_submissions(
    student: User = Depends(require_student), db: Session = Depends(get_db)
) -> list[Submission]:
    return list(db.query(Submission).filter(Submission.student_id == student.id).all())


@router.get("/assignments/{assignment_id}/submissions", response_model=list[SubmissionRead])
def list_submissions(
    assignment_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[Submission]:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    return list(db.query(Submission).filter(Submission.assignment_id == assignment_id).all())


@router.get("/courses/{course_id}/review-queue", response_model=list[EvaluationRead])
def review_queue(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID | None = None,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[Evaluation]:
    require_course_faculty(db, course_id, faculty)
    query = (
        db.query(Evaluation)
        .join(Submission, Submission.id == Evaluation.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .filter(Assignment.course_id == course_id, Evaluation.status == EvalStatus.awaiting_review)
    )
    if assignment_id is not None:
        query = query.filter(Assignment.id == assignment_id)
    return list(query.order_by(Evaluation.created_at.desc()).all())


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetail)
def get_evaluation(
    evaluation_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> EvaluationDetail:
    evaluation = _get_evaluation_or_404(db, evaluation_id)
    _require_evaluation_faculty(db, evaluation, faculty)
    scores = db.query(CriterionScore).filter(CriterionScore.evaluation_id == evaluation.id).all()
    detail = EvaluationDetail.model_validate(evaluation)
    detail.criterion_scores = [CriterionScoreRead.model_validate(s) for s in scores]
    return detail


@router.post("/evaluations/{evaluation_id}/decision")
def evaluation_decision(
    evaluation_id: uuid.UUID,
    payload: EvaluationDecision,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    evaluation = _get_evaluation_or_404(db, evaluation_id)
    _require_evaluation_faculty(db, evaluation, faculty)
    if payload.comment:
        evaluation.faculty_comment = payload.comment
    decision = {
        "approve": payload.approve,
        "final_scores": payload.final_scores or {},
        "feedback": payload.feedback,
        "comment": payload.comment,
    }
    result = evaluation_service.resume_evaluation(db, evaluation, decision, reviewer_id=faculty.id)
    return {"status": result["status"], "evaluation_status": evaluation.status.value}


@router.post("/evaluations/{evaluation_id}/release", response_model=EvaluationRead)
def release_evaluation(
    evaluation_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Evaluation:
    evaluation = _get_evaluation_or_404(db, evaluation_id)
    _require_evaluation_faculty(db, evaluation, faculty)
    if evaluation.status != EvalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only approved evaluations can be released"
        )
    evaluation.released_at = datetime.now(UTC)
    db.commit()
    db.refresh(evaluation)
    return evaluation


@router.get("/submissions/{submission_id}/result", response_model=SubmissionResultRead)
def get_result(
    submission_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> SubmissionResultRead:
    submission = db.get(Submission, submission_id)
    if submission is None or submission.student_id != student.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    evaluation = (
        db.query(Evaluation)
        .filter_by(submission_id=submission.id)
        .order_by(Evaluation.created_at.desc())
        .first()
    )
    if evaluation is None or evaluation.released_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Result not released")
    return SubmissionResultRead(
        submission_id=submission.id,
        status=submission.status,
        total=evaluation.final_total,
        released_at=evaluation.released_at,
    )
