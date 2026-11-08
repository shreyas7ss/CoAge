"""Shared enums (backed by VARCHAR for portability across Postgres/SQLite)."""

from enum import StrEnum


class UserRole(StrEnum):
    student = "student"
    faculty = "faculty"


class QuestionType(StrEnum):
    mcq = "mcq"
    short_answer = "short_answer"
    code = "code"
    open_ended = "open_ended"


class AiPolicy(StrEnum):
    prohibited = "prohibited"
    allowed_with_disclosure = "allowed_with_disclosure"
    encouraged = "encouraged"


class SubmissionStatus(StrEnum):
    not_submitted = "not_submitted"
    submitted = "submitted"
    under_evaluation = "under_evaluation"
    pending_review = "pending_review"
    graded = "graded"
    needs_attention = "needs_attention"


class EvalStatus(StrEnum):
    running = "running"
    awaiting_review = "awaiting_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"
