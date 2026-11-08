"""Course, enrollment, and topic models."""

import uuid

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    faculty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    term: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_enrollment_course_student"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=1.0)
