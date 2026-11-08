"""Assignment, question, grading package, and rubric criterion models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
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
from app.models.enums import AiPolicy, QuestionType


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allow_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    late_penalty_pct: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    max_marks: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    grade_weight: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    ai_policy: Mapped[AiPolicy] = mapped_column(
        Enum(AiPolicy, native_enum=False, length=32), nullable=False, default=AiPolicy.prohibited
    )
    require_understanding_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    active_package_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    qtype: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, length=20), nullable=False
    )
    max_marks: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    mcq_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mcq_correct: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    test_cases: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GradingPackage(Base, TimestampMixin):
    __tablename__ = "grading_packages"
    __table_args__ = (
        UniqueConstraint("assignment_id", "version", name="uq_package_assignment_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # draft | approved
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RubricCriterion(Base, TimestampMixin):
    __tablename__ = "rubric_criteria"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id"), nullable=False, index=True
    )
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    topic_weight: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=1.0)
