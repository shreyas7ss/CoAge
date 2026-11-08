"""User schemas."""

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    roll_no: str | None = None
