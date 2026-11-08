"""Database adapter for faculty analytics; formulas remain in ``metrics``."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.metrics import mastery_ema, topic_score
from app.core.config import settings
from app.models.analytics import TopicMastery, TopicMasteryEvent
from app.models.assignment import Assignment, Question, RubricCriterion
from app.models.enums import EvalStatus
from app.models.submission import CriterionScore, Evaluation, Submission


def recompute_mastery(db: Session, student_id: uuid.UUID, topic_id: uuid.UUID) -> TopicMastery:
    events = (
        db.query(TopicMasteryEvent)
        .filter_by(student_id=student_id, topic_id=topic_id)
        .order_by(TopicMasteryEvent.created_at, TopicMasteryEvent.id)
        .all()
    )
    result = mastery_ema([float(event.score) for event in events], settings.mastery_ema_alpha)
    row = db.get(TopicMastery, (student_id, topic_id))
    if row is None:
        row = TopicMastery(
            student_id=student_id, topic_id=topic_id, **result, updated_at=datetime.now(UTC)
        )
        db.add(row)
    else:
        row.mastery = float(result["mastery"])
        row.confidence = float(result["confidence"])
        row.n_events = int(result["n_events"])
        row.updated_at = datetime.now(UTC)
    return row


def write_mastery_events(db: Session, submission: Submission, evaluation: Evaluation) -> None:
    """Record one final-score event per tagged topic and refresh the rollups."""
    rows = (
        db.query(CriterionScore, RubricCriterion)
        .join(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .filter(CriterionScore.evaluation_id == evaluation.id)
        .all()
    )
    by_topic: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for score, criterion in rows:
        if criterion.topic_id is None:
            continue
        by_topic.setdefault(criterion.topic_id, []).append(
            {
                "topic_id": criterion.topic_id,
                "topic_weight": float(criterion.topic_weight),
                "final_awarded": float(score.final_awarded or 0),
                "max_marks": float(score.max_marks or criterion.marks),
            }
        )
    for topic_id, criteria in by_topic.items():
        value = topic_score(criteria, str(topic_id))
        if value is None:
            continue
        db.add(
            TopicMasteryEvent(
                student_id=submission.student_id,
                topic_id=topic_id,
                submission_id=submission.id,
                score=value,
                evidence_weight=1.0,
            )
        )
        db.flush()
        recompute_mastery(db, submission.student_id, topic_id)


def approved_evaluation_rows(
    db: Session, course_id: uuid.UUID, assignment_id: uuid.UUID | None = None
):
    query = (
        db.query(Evaluation, Submission, Assignment)
        .join(Submission, Submission.id == Evaluation.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .filter(Assignment.course_id == course_id, Evaluation.status == EvalStatus.approved)
    )
    if assignment_id is not None:
        query = query.filter(Assignment.id == assignment_id)
    return query.all()


def score_rows(db: Session, evaluation_ids: list[uuid.UUID]):
    if not evaluation_ids:
        return []
    return (
        db.query(CriterionScore, RubricCriterion, Question)
        .outerjoin(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .outerjoin(Question, Question.id == RubricCriterion.question_id)
        .filter(CriterionScore.evaluation_id.in_(evaluation_ids))
        .all()
    )


def topic_cell_scores(db: Session, evaluations: list[tuple[Evaluation, Submission, Assignment]]):
    grouped: dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, list[dict[str, Any]]]] = {}
    rows = score_rows(db, [e.id for e, _, _ in evaluations])
    for score, criterion, _question in rows:
        if criterion is None or criterion.topic_id is None or score.final_awarded is None:
            continue
        assignment_id = next(a.id for _e, _s, a in evaluations if _e.id == score.evaluation_id)
        submission_id = next(s.id for e, s, _a in evaluations if e.id == score.evaluation_id)
        grouped.setdefault((criterion.topic_id, assignment_id), {}).setdefault(
            submission_id, []
        ).append(
            {
                "topic_id": criterion.topic_id,
                "topic_weight": float(criterion.topic_weight),
                "final_awarded": float(score.final_awarded),
                "max_marks": float(score.max_marks or criterion.marks),
            }
        )
    result = {}
    for key, submissions in grouped.items():
        values = [topic_score(criteria, str(key[0])) for criteria in submissions.values()]
        result[key] = [float(value) for value in values if value is not None]
    return result
