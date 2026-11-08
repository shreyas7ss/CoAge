"""LLM structured-output schemas (used with ``.with_structured_output``)."""

from pydantic import BaseModel, Field


class DraftedCriterion(BaseModel):
    criterion: str
    marks: float
    topic: str  # topic id, constrained to the course's topics
    topic_weight: float = 1.0


class DraftedQuestion(BaseModel):
    q_id: str
    reference_answer: str
    acceptable_alternatives: str = ""
    common_misconceptions: list[str] = Field(default_factory=list)
    rubric: list[DraftedCriterion]


class DraftedPackage(BaseModel):
    questions: list[DraftedQuestion]


class CriterionResult(BaseModel):
    """Per-criterion grading result (0 <= awarded <= max_marks)."""

    awarded: float = Field(ge=0)
    evidence: str
    matched_misconception: str | None = None
    reasoning: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)


class FeedbackDraft(BaseModel):
    """Reviewer-facing rationale + student-facing feedback draft."""

    rationale: str = ""
    feedback: str = ""


class FeedbackGeneration(BaseModel):
    """Personalized released feedback; contains no marks or authenticity verdicts."""

    feedback: str
    misconceptions: list[str] = Field(default_factory=list)
    suggested_practice: list[str] = Field(default_factory=list, min_length=2, max_length=3)


class MonitoringDigest(BaseModel):
    digest: str = ""
