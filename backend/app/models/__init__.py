"""Import all models so ``Base.metadata`` is fully populated for Alembic/tests."""

from app.models.analytics import FollowupCheck, TopicMastery, TopicMasteryEvent
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.authenticity import (
    AuthenticityReport,
    CorrectionMemory,
    ProcessEvent,
    WritingBaseline,
)
from app.models.communication import Alert, Feedback
from app.models.course import Course, Enrollment, Topic
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer
from app.models.user import User

__all__ = [
    "User",
    "Course",
    "Enrollment",
    "Topic",
    "Assignment",
    "Question",
    "GradingPackage",
    "RubricCriterion",
    "Submission",
    "SubmissionAnswer",
    "Evaluation",
    "CriterionScore",
    "TopicMasteryEvent",
    "TopicMastery",
    "FollowupCheck",
    "Feedback",
    "Alert",
    "AuthenticityReport",
    "WritingBaseline",
    "ProcessEvent",
    "CorrectionMemory",
]
