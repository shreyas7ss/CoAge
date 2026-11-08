"""Submission and evaluation schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import EvalStatus, SubmissionStatus


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    submitted_at: datetime | None = None
    is_late: bool
    status: SubmissionStatus
    ai_disclosure: str | None = None


class SubmissionResultRead(BaseModel):
    submission_id: uuid.UUID
    status: SubmissionStatus
    total: float | None
    released_at: datetime | None = None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    text: str
    misconceptions: list[str]
    suggested_practice: list[str]
    released_at: datetime | None = None


class CriterionScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    criterion_id: uuid.UUID | None
    ai_awarded: float | None
    final_awarded: float | None
    max_marks: float | None
    evidence: str | None
    matched_misconception: str | None
    confidence: float | None
    needs_manual: bool
    faculty_note: str | None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    package_version: int
    model: str | None = None
    ai_total: float | None
    final_total: float | None
    confidence: float | None
    status: EvalStatus
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    released_at: datetime | None = None
    faculty_comment: str | None = None


class EvaluationDetail(EvaluationRead):
    criterion_scores: list[CriterionScoreRead] = []
    submission_answers: list[dict] = []


class EvaluationDecision(BaseModel):
    approve: bool = True
    final_scores: dict[str, float] | None = None
    criterion_notes: dict[str, str] | None = None
    feedback: str | None = None
    comment: str | None = None
