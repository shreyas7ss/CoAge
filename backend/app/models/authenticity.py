"""Faculty-only authenticity evidence and co-learning correction memory."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.authenticity.signals import EMBEDDING_DIMENSIONS
from app.db.base import Base, TimestampMixin


class AuthenticityReport(Base, TimestampMixin):
    __tablename__ = "authenticity_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, unique=True, index=True
    )
    concern_level: Mapped[str] = mapped_column(String(32), nullable=False)
    signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    caveats: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reviewed: Mapped[bool] = mapped_column(default=False, nullable=False)
    baseline_updated: Mapped[bool] = mapped_column(default=False, nullable=False)
    faculty_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class WritingBaseline(Base):
    __tablename__ = "writing_baselines"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    features: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProcessEvent(Base, TimestampMixin):
    __tablename__ = "process_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CorrectionMemory(Base, TimestampMixin):
    __tablename__ = "correction_memory"
    __table_args__ = (Index("ix_correction_memory_signature", "criterion_signature"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    criterion_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    student_text_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    ai_awarded: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    final_awarded: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    faculty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS).with_variant(JSON(), "sqlite"), nullable=False
    )
