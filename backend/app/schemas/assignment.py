"""Assignment, question, and grading-package schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AiPolicy, QuestionType


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    deadline: datetime
    allow_late: bool = True
    late_penalty_pct: float = 0.0
    max_marks: float = Field(gt=0)
    grade_weight: float = 0.0
    ai_policy: AiPolicy = AiPolicy.prohibited
    require_understanding_check: bool = False
    auto_draft: bool = False
    questions: list["QuestionCreate"] = Field(default_factory=list)


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    allow_late: bool | None = None
    late_penalty_pct: float | None = None
    max_marks: float | None = None
    grade_weight: float | None = None
    ai_policy: AiPolicy | None = None
    require_understanding_check: bool | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None = None
    deadline: datetime
    allow_late: bool
    late_penalty_pct: float
    max_marks: float
    grade_weight: float
    ai_policy: AiPolicy
    require_understanding_check: bool
    status: str
    active_package_version: int | None = None


class QuestionCreate(BaseModel):
    position: int
    prompt: str
    qtype: QuestionType
    max_marks: float = Field(ge=0)
    mcq_options: list | None = None
    mcq_correct: list | None = None
    test_cases: list | None = None


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    position: int
    prompt: str
    qtype: QuestionType
    max_marks: float
    mcq_options: list | None = None
    mcq_correct: list | None = None
    test_cases: list | None = None


class QuestionsBulkRequest(BaseModel):
    questions: list[QuestionCreate]


class PackageDecision(BaseModel):
    approved: bool
    package: dict | None = None
    comments: str | None = None


class PackageDraftUpdate(BaseModel):
    content: dict


class PackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    version: int
    status: str
    content: dict
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
