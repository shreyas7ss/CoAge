"""User model."""

import uuid

from sqlalchemy import Boolean, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), nullable=False
    )
    roll_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Optional, self-reported; used ONLY to attach caveats to authenticity reports.
    native_english: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
