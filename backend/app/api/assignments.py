"""Assignments, questions, and grading-package router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    require_course_faculty,
    require_course_member,
    require_faculty,
)
from app.db.session import get_db
from app.models.assignment import Assignment, GradingPackage, Question
from app.models.course import Enrollment
from app.models.enums import UserRole
from app.models.submission import Submission
from app.models.user import User
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
    PackageDecision,
    PackageDraftUpdate,
    PackageRead,
    QuestionRead,
    QuestionsBulkRequest,
)
from app.services import setup_service
from app.services.parsing import extract_text_from_pdf, parse_questions

router = APIRouter(tags=["assignments"])


def _get_assignment_or_404(db: Session, assignment_id: uuid.UUID) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment


def _ensure_draft(assignment: Assignment) -> None:
    if assignment.active_package_version is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assignment is locked (an approved package exists)",
        )


@router.get("/courses/{course_id}/assignments", response_model=list[AssignmentRead])
def list_assignments(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Assignment]:
    require_course_member(db, course_id, current_user)
    query = db.query(Assignment).filter(Assignment.course_id == course_id)
    if current_user.role == UserRole.student:
        query = query.filter(Assignment.status == "published")
    return list(query.order_by(Assignment.created_at).all())


@router.post(
    "/courses/{course_id}/assignments",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    course_id: uuid.UUID,
    payload: AssignmentCreate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Assignment:
    require_course_faculty(db, course_id, faculty)
    assignment = Assignment(
        course_id=course_id,
        title=payload.title,
        description=payload.description,
        deadline=payload.deadline,
        allow_late=payload.allow_late,
        late_penalty_pct=payload.late_penalty_pct,
        max_marks=payload.max_marks,
        grade_weight=payload.grade_weight,
        ai_policy=payload.ai_policy,
        require_understanding_check=payload.require_understanding_check,
        status="draft",
    )
    db.add(assignment)
    db.flush()
    for question in payload.questions:
        db.add(
            Question(
                assignment_id=assignment.id,
                position=question.position,
                prompt=question.prompt,
                qtype=question.qtype,
                max_marks=question.max_marks,
                mcq_options=question.mcq_options,
                mcq_correct=question.mcq_correct,
                test_cases=question.test_cases,
            )
        )
    db.commit()
    db.refresh(assignment)

    if payload.auto_draft and payload.questions:
        setup_service.start_setup(db, assignment)
    return assignment


@router.get("/assignments/{assignment_id}", response_model=AssignmentRead)
def get_assignment(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_member(db, assignment.course_id, current_user)
    if current_user.role == UserRole.student and assignment.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment


@router.get("/assignments/{assignment_id}/questions", response_model=list[QuestionRead])
def list_assignment_questions(
    assignment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Question]:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_member(db, assignment.course_id, current_user)
    if current_user.role == UserRole.student and assignment.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return list(
        db.query(Question).filter_by(assignment_id=assignment.id).order_by(Question.position).all()
    )


@router.get("/assignments/{assignment_id}/completeness")
def assignment_completeness(
    assignment_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    enrolled = (
        db.query(User)
        .join(Enrollment, Enrollment.student_id == User.id)
        .filter(Enrollment.course_id == assignment.course_id)
        .order_by(User.full_name)
        .all()
    )
    submissions = {
        row.student_id: row
        for row in db.query(Submission).filter_by(assignment_id=assignment.id).all()
    }
    rows = []
    for student in enrolled:
        submission = submissions.get(student.id)
        state = (
            "missing"
            if submission is None or submission.submitted_at is None
            else "late"
            if submission.is_late
            else submission.status.value
        )
        rows.append(
            {
                "student_id": str(student.id),
                "student_name": student.full_name,
                "email": student.email,
                "status": state,
                "submitted_at": submission.submitted_at.isoformat()
                if submission and submission.submitted_at
                else None,
            }
        )
    return {"assignment_id": str(assignment.id), "students": rows}


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    _ensure_draft(assignment)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/assignments/{assignment_id}/questions", response_model=list[QuestionRead])
def replace_questions(
    assignment_id: uuid.UUID,
    payload: QuestionsBulkRequest,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[Question]:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    _ensure_draft(assignment)
    db.query(Question).filter(Question.assignment_id == assignment_id).delete()
    for question in payload.questions:
        db.add(
            Question(
                assignment_id=assignment_id,
                position=question.position,
                prompt=question.prompt,
                qtype=question.qtype,
                max_marks=question.max_marks,
                mcq_options=question.mcq_options,
                mcq_correct=question.mcq_correct,
                test_cases=question.test_cases,
            )
        )
    db.commit()
    return list(
        db.query(Question)
        .filter(Question.assignment_id == assignment_id)
        .order_by(Question.position)
        .all()
    )


@router.post("/assignments/{assignment_id}/question-paper", response_model=list[QuestionRead])
async def upload_question_paper(
    assignment_id: uuid.UUID,
    file: UploadFile,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[Question]:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    _ensure_draft(assignment)
    content = await file.read()
    if file.filename and file.filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf(content)
    else:
        text = content.decode("utf-8", errors="replace")
    parsed = parse_questions(text)

    db.query(Question).filter(Question.assignment_id == assignment_id).delete()
    for item in parsed:
        db.add(
            Question(
                assignment_id=assignment_id,
                position=item["position"],
                prompt=item["prompt"],
                qtype=item["qtype"],
                max_marks=0,
            )
        )
    db.commit()
    return list(
        db.query(Question)
        .filter(Question.assignment_id == assignment_id)
        .order_by(Question.position)
        .all()
    )


@router.get("/assignments/{assignment_id}/package", response_model=list[PackageRead])
def list_packages(
    assignment_id: uuid.UUID,
    version: int | None = None,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[GradingPackage]:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    query = db.query(GradingPackage).filter(GradingPackage.assignment_id == assignment_id)
    if version is not None:
        query = query.filter(GradingPackage.version == version)
    return list(query.order_by(GradingPackage.version).all())


@router.put("/assignments/{assignment_id}/package/draft", response_model=PackageRead)
def update_package_draft(
    assignment_id: uuid.UUID,
    payload: PackageDraftUpdate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> GradingPackage:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    _ensure_draft(assignment)
    draft = setup_service.save_draft(db, assignment, payload.content)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/assignments/{assignment_id}/package/start")
def start_package_setup(
    assignment_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    """Start the setup graph (AI drafting + validation) and pause at faculty review."""
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    _ensure_draft(assignment)
    result = setup_service.start_setup(db, assignment)
    if result["status"] == "interrupted":
        payload = result["interrupt"][0]
        return {
            "status": "interrupted",
            "package": payload.get("package"),
            "validation_errors": payload.get("validation_errors", []),
        }
    return {"status": result["status"]}


@router.post("/assignments/{assignment_id}/package/decision")
def package_decision(
    assignment_id: uuid.UUID,
    payload: PackageDecision,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    if assignment.setup_thread_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup not started; call /package/start first",
        )
    decision = payload.model_dump()
    result = setup_service.resume_setup(db, assignment, decision, approved_by=faculty.id)
    return {
        "status": result["status"],
        "package_version": assignment.active_package_version,
    }


@router.post("/assignments/{assignment_id}/publish", response_model=AssignmentRead)
def publish_assignment(
    assignment_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = _get_assignment_or_404(db, assignment_id)
    require_course_faculty(db, assignment.course_id, faculty)
    if assignment.active_package_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot publish without an approved grading package",
        )
    assignment.status = "published"
    db.commit()
    db.refresh(assignment)
    return assignment
