"""Assignment setup service: orchestrate the setup graph and persist packages."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.common import runner
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.course import Topic

DRAFT_VERSION = 0  # mutable draft; approved versions start at 1


def _load_questions(db: Session, assignment_id: uuid.UUID) -> list[dict]:
    questions = (
        db.query(Question)
        .filter(Question.assignment_id == assignment_id)
        .order_by(Question.position)
        .all()
    )
    return [
        {
            "q_id": str(q.id),
            "prompt": q.prompt,
            "qtype": q.qtype.value,
            "max_marks": float(q.max_marks),
        }
        for q in questions
    ]


def _load_topics(db: Session, course_id: uuid.UUID) -> list[dict]:
    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    return [{"id": str(t.id), "name": t.name} for t in topics]


def build_input_state(
    db: Session, assignment: Assignment, skip_draft: bool, package_draft: dict | None
) -> dict:
    return {
        "assignment_id": str(assignment.id),
        "course_topics": _load_topics(db, assignment.course_id),
        "questions": _load_questions(db, assignment.id),
        "package_draft": package_draft,
        "skip_draft": skip_draft,
        "rejection_count": 0,
        "validation_errors": [],
    }


def start_setup(db: Session, assignment: Assignment, *, package_draft: dict | None = None) -> dict:
    """Run the setup graph until it interrupts (faculty review)."""
    thread_id = f"setup-{assignment.id}"
    state = build_input_state(
        db, assignment, skip_draft=package_draft is not None, package_draft=package_draft
    )
    result = runner.start("setup", thread_id, state)
    assignment.setup_thread_id = thread_id
    if result["status"] == "interrupted":
        draft = result["interrupt"][0].get("package")
        if draft is not None:
            save_draft(db, assignment, draft)
    db.commit()
    return result


def resume_setup(
    db: Session, assignment: Assignment, decision: dict, approved_by: uuid.UUID
) -> dict:
    """Resume the setup graph with the faculty decision; lock on approval."""
    thread_id = assignment.setup_thread_id or f"setup-{assignment.id}"
    assignment.setup_thread_id = thread_id
    result = runner.resume("setup", thread_id, decision)
    if result["status"] == "finished":
        final_package = result["state"].get("final_package")
        status = result["state"].get("status")
        if status == "approved" and final_package:
            lock_package(db, assignment, final_package, approved_by)
        elif final_package is not None:
            save_draft(db, assignment, final_package)
    elif result["status"] == "interrupted":
        draft = result["interrupt"][0].get("package")
        if draft is not None:
            save_draft(db, assignment, draft)
    db.commit()
    return result


def save_draft(db: Session, assignment: Assignment, package: dict) -> GradingPackage:
    draft = (
        db.query(GradingPackage)
        .filter_by(assignment_id=assignment.id, version=DRAFT_VERSION)
        .first()
    )
    if draft is None:
        draft = GradingPackage(
            assignment_id=assignment.id, version=DRAFT_VERSION, status="draft", content=package
        )
        db.add(draft)
    else:
        draft.content = package
    return draft


def _next_version(db: Session, assignment_id: uuid.UUID) -> int:
    current = (
        db.query(func.max(GradingPackage.version))
        .filter(GradingPackage.assignment_id == assignment_id, GradingPackage.version >= 1)
        .scalar()
    )
    return (current or 0) + 1


def lock_package(
    db: Session, assignment: Assignment, package: dict, approved_by: uuid.UUID
) -> GradingPackage:
    """Create an approved, immutable package version and copy rubric criteria."""
    version = _next_version(db, assignment.id)
    pkg = GradingPackage(
        assignment_id=assignment.id,
        version=version,
        status="approved",
        content=package,
        approved_by=approved_by,
        approved_at=datetime.now(UTC),
    )
    db.add(pkg)
    db.flush()

    question_by_qid = {
        str(q.id): q
        for q in db.query(Question).filter(Question.assignment_id == assignment.id).all()
    }
    for question in package.get("questions", []):
        qrow = question_by_qid.get(question.get("q_id"))
        if qrow is None:
            continue
        rubric = question.get("rubric") or []
        if not rubric:
            # Deterministic questions (e.g. mcq) have no rubric; synthesize one
            # criterion so every question is uniformly represented in criterion_scores.
            rubric = [{"criterion": "Correct answer", "marks": float(qrow.max_marks)}]
        for criterion in rubric:
            topic_str = criterion.get("topic")
            topic_id = uuid.UUID(topic_str) if topic_str else None
            db.add(
                RubricCriterion(
                    question_id=qrow.id,
                    package_version=version,
                    description=criterion.get("criterion", ""),
                    marks=float(criterion.get("marks", 0)),
                    topic_id=topic_id,
                    topic_weight=float(criterion.get("topic_weight", 1.0)),
                )
            )

    assignment.active_package_version = version
    _delete_draft(db, assignment.id)
    return pkg


def _delete_draft(db: Session, assignment_id: uuid.UUID) -> None:
    draft = (
        db.query(GradingPackage)
        .filter_by(assignment_id=assignment_id, version=DRAFT_VERSION)
        .first()
    )
    if draft is not None:
        db.delete(draft)
