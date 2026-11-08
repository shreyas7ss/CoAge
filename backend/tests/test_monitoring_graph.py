"""Monitoring checks are deterministic; only the digest uses a model."""

from datetime import UTC, datetime, timedelta

from app.agents.monitoring.graph import build_monitoring_graph
from app.schemas.llm import MonitoringDigest
from tests.fake_llm import FakeLLM


def test_monitoring_rules_and_alert_deduplication() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    upcoming_id = "assignment-upcoming"
    overdue_id = "assignment-overdue"
    weak_topic = "topic-weak"
    llm = FakeLLM(
        {MonitoringDigest: lambda: MonitoringDigest(digest="Review these course alerts.")}
    )
    graph = build_monitoring_graph(llm_factory=lambda: llm)
    result = graph.invoke(
        {
            "course_id": "course-1",
            "now": now.isoformat(),
            "alerts": [],
            "assignments": [
                {
                    "assignment_id": upcoming_id,
                    "title": "Upcoming",
                    "deadline": (now + timedelta(hours=12)).isoformat(),
                    "enrollment_count": 4,
                    "submitted_count": 1,
                    "enrolled_student_ids": [],
                    "submitted_student_ids": [],
                },
                {
                    "assignment_id": overdue_id,
                    "title": "Past due",
                    "deadline": (now - timedelta(days=1)).isoformat(),
                    "enrollment_count": 2,
                    "submitted_count": 0,
                    "enrolled_student_ids": ["s1", "s2"],
                    "submitted_student_ids": [],
                },
            ],
            "review_backlog": [
                {"evaluation_id": "e1", "assignment_id": overdue_id, "days_waiting": 4}
            ],
            "at_risk_students": [
                {"student_id": "s1", "at_risk": True, "payload": {"missed_submissions": 2}}
            ],
            "weak_topics": [
                {"topic_id": weak_topic, "name": "Hashing", "n": 8, "below_fraction": 0.5}
            ],
            "open_alert_keys": [("weak_topic", None, None, weak_topic)],
        }
    )
    kinds = [alert["kind"] for alert in result["new_alerts"]]
    assert kinds.count("missing") == 2
    assert "due_soon_low_rate" in kinds
    assert "overdue_review" in kinds
    assert "at_risk" in kinds
    assert "weak_topic" not in kinds
    assert result["digest"] == "Review these course alerts."
    assert llm.calls == [MonitoringDigest]


def test_monitoring_without_alerts_does_not_call_llm() -> None:
    llm = FakeLLM()
    graph = build_monitoring_graph(llm_factory=lambda: llm)
    result = graph.invoke({"alerts": [], "open_alert_keys": []})
    assert result["new_alerts"] == []
    assert result["digest"] == "No new alerts."
    assert llm.calls == []
