"""Load deterministic course signals, run monitoring, and persist deduplicated alerts."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.common import runner
from app.analytics.metrics import below_threshold, mastery_trend, student_flags
from app.core.config import settings
from app.models.analytics import TopicMastery, TopicMasteryEvent
from app.models.assignment import Assignment
from app.models.communication import Alert
from app.models.course import Enrollment, Topic
from app.models.enums import EvalStatus
from app.models.submission import Evaluation, Submission


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def build_monitoring_state(db: Session, course_id: uuid.UUID, now: datetime | None = None) -> dict:
    current = now or datetime.now(UTC)
    enrollment_ids = [
        str(row[0]) for row in db.query(Enrollment.student_id).filter_by(course_id=course_id)
    ]
    assignments = db.query(Assignment).filter_by(course_id=course_id, status="published").all()
    submissions = (
        db.query(Submission)
        .filter(Submission.assignment_id.in_([assignment.id for assignment in assignments]))
        .all()
        if assignments
        else []
    )
    by_assignment: dict[uuid.UUID, list[Submission]] = defaultdict(list)
    for submission in submissions:
        by_assignment[submission.assignment_id].append(submission)
    assignment_data = []
    for assignment in assignments:
        related = by_assignment[assignment.id]
        assignment_data.append(
            {
                "assignment_id": str(assignment.id),
                "title": assignment.title,
                "deadline": _utc(assignment.deadline).isoformat(),
                "enrollment_count": len(enrollment_ids),
                "submitted_count": sum(sub.submitted_at is not None for sub in related),
                "enrolled_student_ids": enrollment_ids,
                "submitted_student_ids": [
                    str(sub.student_id) for sub in related if sub.submitted_at
                ],
            }
        )

    reviews = (
        db.query(Evaluation, Submission)
        .join(Submission, Submission.id == Evaluation.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .filter(Assignment.course_id == course_id, Evaluation.status == EvalStatus.awaiting_review)
        .all()
    )
    backlog = []
    for evaluation, submission in reviews:
        age = (current - _utc(evaluation.created_at)).total_seconds() / 86400
        backlog.append(
            {
                "evaluation_id": str(evaluation.id),
                "assignment_id": str(submission.assignment_id),
                "days_waiting": age,
            }
        )

    mastery_rows = (
        db.query(TopicMastery)
        .join(Topic, Topic.id == TopicMastery.topic_id)
        .filter(
            Topic.course_id == course_id,
            TopicMastery.student_id.in_([uuid.UUID(student_id) for student_id in enrollment_ids]),
        )
        .all()
        if enrollment_ids
        else []
    )
    by_student: dict[uuid.UUID, list[dict]] = defaultdict(list)
    by_topic: dict[uuid.UUID, list[float]] = defaultdict(list)
    for row in mastery_rows:
        by_student[row.student_id].append(
            {
                "topic_id": str(row.topic_id),
                "mastery": float(row.mastery),
                "confidence": float(row.confidence),
            }
        )
        by_topic[row.topic_id].append(float(row.mastery))

    due = [assignment for assignment in assignments if _utc(assignment.deadline) < current]
    submissions_by_student_assignment = {(sub.student_id, sub.assignment_id) for sub in submissions}
    missing_by_student = {
        student_id: sum(
            (student_id, assignment.id) not in submissions_by_student_assignment
            for assignment in due
        )
        for student_id in (uuid.UUID(value) for value in enrollment_ids)
    }
    events = (
        db.query(TopicMasteryEvent)
        .join(Topic, Topic.id == TopicMasteryEvent.topic_id)
        .filter(
            Topic.course_id == course_id,
            TopicMasteryEvent.student_id.in_([uuid.UUID(v) for v in enrollment_ids]),
        )
        .order_by(TopicMasteryEvent.created_at)
        .all()
        if enrollment_ids
        else []
    )
    events_by_submission: dict[uuid.UUID, list[float]] = defaultdict(list)
    for event in events:
        events_by_submission[event.submission_id].append(float(event.score))
    assignment_order = {assignment.id: _utc(assignment.deadline) for assignment in assignments}
    risk_students = []
    for student_id in (uuid.UUID(value) for value in enrollment_ids):
        event_scores = []
        assignment_scores: dict[uuid.UUID, list[float]] = defaultdict(list)
        for submission_id, scores in events_by_submission.items():
            sub = next((s for s in submissions if s.id == submission_id), None)
            if sub is not None and sub.student_id == student_id:
                assignment_scores[sub.assignment_id].extend(scores)
        for _assignment_id, scores in sorted(
            assignment_scores.items(), key=lambda pair: assignment_order[pair[0]]
        ):
            event_scores.append(sum(scores) / len(scores))
        trend = mastery_trend(event_scores)
        flags = student_flags(
            by_student.get(student_id, []),
            missing_by_student[student_id],
            trend,
            settings.weak_topic_threshold,
        )
        risk_students.append(
            {
                "student_id": str(student_id),
                "at_risk": flags["at_risk"],
                "payload": {
                    "weak_topic_count": len(flags["weak_topic_ids"]),
                    "missed_submissions": flags["missed_submissions"],
                    "trend": flags["trend"],
                },
            }
        )

    topic_names = {
        topic.id: topic.name for topic in db.query(Topic).filter_by(course_id=course_id).all()
    }
    weak_topics = []
    for topic_id, values in by_topic.items():
        stats = below_threshold(values, settings.weak_topic_threshold)
        weak_topics.append(
            {
                "topic_id": str(topic_id),
                "name": topic_names.get(topic_id),
                "n": stats["n"],
                "below_fraction": stats["fraction"] or 0.0,
            }
        )

    open_alerts = db.query(Alert).filter_by(course_id=course_id, status="open").all()
    return {
        "course_id": str(course_id),
        "now": current.isoformat(),
        "assignments": assignment_data,
        "review_backlog": backlog,
        "at_risk_students": risk_students,
        "weak_topics": weak_topics,
        "open_alert_keys": [
            (
                alert.kind,
                str(alert.target_student_id) if alert.target_student_id else None,
                str(alert.target_assignment_id) if alert.target_assignment_id else None,
                str(alert.topic_id) if alert.topic_id else None,
            )
            for alert in open_alerts
        ],
        "alerts": [],
    }


def run_monitoring(db: Session, course_id: uuid.UUID, now: datetime | None = None) -> dict:
    state = build_monitoring_state(db, course_id, now)
    thread_id = f"monitor-{course_id}-{int(datetime.now(UTC).timestamp())}"
    result = runner.start("monitoring", thread_id, state)
    if result["status"] != "finished":
        raise RuntimeError("monitoring graph did not finish")
    final = result["state"]
    saved = []
    for alert_data in final.get("new_alerts", []):
        alert = Alert(
            course_id=course_id,
            kind=alert_data["kind"],
            target_student_id=uuid.UUID(alert_data["target_student_id"])
            if alert_data.get("target_student_id")
            else None,
            target_assignment_id=uuid.UUID(alert_data["target_assignment_id"])
            if alert_data.get("target_assignment_id")
            else None,
            topic_id=uuid.UUID(alert_data["topic_id"]) if alert_data.get("topic_id") else None,
            payload=alert_data.get("payload", {}),
            status="open",
        )
        db.add(alert)
        saved.append(alert)
    db.commit()
    return {
        "status": "finished",
        "created": len(saved),
        "digest": final.get("digest", ""),
        "digest_fallback": bool(final.get("digest_fallback", False)),
        "alerts": saved,
    }
