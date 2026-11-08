"""Test helpers for building users and auth headers."""

import uuid

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.enums import UserRole
from app.models.user import User

DEFAULT_PASSWORD = "password"


def make_user(
    db: Session,
    *,
    role: UserRole,
    email: str | None = None,
    full_name: str = "Test User",
    roll_no: str | None = None,
) -> User:
    user = User(
        email=email or f"{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(DEFAULT_PASSWORD),
        full_name=full_name,
        role=role,
        roll_no=roll_no,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}
