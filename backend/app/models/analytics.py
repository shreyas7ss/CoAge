"""Persisted topic mastery events and their recomputable rollup."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TopicMasteryEvent(Base, TimestampMixin):
    __tablename__ = "topic_mastery_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), nullable=False, index=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    evidence_weight: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=1.0)


class TopicMastery(Base):
    __tablename__ = "topic_mastery"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"), primary_key=True)
    mastery: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    n_events: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FollowupCheck(Base, TimestampMixin):
    """Student understanding follow-up record used by Phase 6 and gap analytics."""

    __tablename__ = "followup_checks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    questions: Mapped[list] = mapped_column(JSON, nullable=False)
    answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_limit_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retake_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
