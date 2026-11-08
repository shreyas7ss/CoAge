"""Submission, submission answer, evaluation, and criterion score models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import EvalStatus, SubmissionStatus


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=24),
        nullable=False,
        default=SubmissionStatus.not_submitted,
    )
    file_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ai_disclosure: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SubmissionAnswer(Base, TimestampMixin):
    __tablename__ = "submission_answers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id"), nullable=False, index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    # NOTE: `embedding vector(1024)` is added in the authenticity phase (pgvector).


class Evaluation(Base, TimestampMixin):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_total: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    final_total: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[EvalStatus] = mapped_column(
        Enum(EvalStatus, native_enum=False, length=24), nullable=False, default=EvalStatus.running
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    faculty_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class CriterionScore(Base, TimestampMixin):
    __tablename__ = "criterion_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False, index=True
    )
    criterion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rubric_criteria.id"), nullable=True
    )
    ai_awarded: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    final_awarded: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_marks: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_misconception: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    needs_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    faculty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
