"""API contracts for faculty signals and student follow-up checks."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthenticityReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    concern_level: str
    signals: list[dict]
    caveats: list[str]
    policy: dict
    reviewed: bool
    faculty_note: str | None


class AuthenticityReview(BaseModel):
    action: Literal["no_concern", "note"]
    note: str | None = Field(default=None, max_length=2000)


class ProcessLoggingUpdate(BaseModel):
    enabled: bool


class ProcessEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["paste", "revision", "draft_save", "session_summary"]
    count: int = Field(default=1, ge=0, le=100000)
    meta: dict[str, float] = Field(default_factory=dict)


class FollowupRead(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    questions: list[str]
    issued_at: datetime | None
    time_limit_sec: int | None
    retake_count: int


class FollowupAnswers(BaseModel):
    answers: list[str] = Field(min_length=2, max_length=3)
