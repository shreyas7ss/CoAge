"""Deterministic monitoring checks; the LLM only summarizes new alerts."""

import operator
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.llm import MonitoringDigest


class MonitoringState(TypedDict, total=False):
    course_id: str
    now: str
    assignments: list[dict]
    scanned_deadlines: list[dict]
    review_backlog: list[dict]
    at_risk_students: list[dict]
    weak_topics: list[dict]
    open_alert_keys: list[tuple]
    alerts: Annotated[list[dict], operator.add]
    new_alerts: list[dict]
    digest: str


def alert_key(alert: dict) -> tuple:
    return (
        alert.get("kind"),
        alert.get("target_student_id"),
        alert.get("target_assignment_id"),
        alert.get("topic_id"),
    )


def build_monitoring_graph(llm_factory: Any = None, checkpointer: Any = None):
    from app.agents.common.llm import get_llm

    llm_factory = llm_factory or get_llm

    def scan_deadlines(state: MonitoringState) -> dict:
        now = datetime.fromisoformat(state.get("now") or datetime.now(UTC).isoformat())
        scanned = []
        for assignment in state.get("assignments", []):
            deadline = datetime.fromisoformat(assignment["deadline"])
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            hours_left = (deadline - now).total_seconds() / 3600
            if 0 <= hours_left <= 72:
                scanned.append({**assignment, "hours_left": hours_left})
        return {"scanned_deadlines": scanned}

    def find_missing_and_late(state: MonitoringState) -> dict:
        now = datetime.fromisoformat(state.get("now") or datetime.now(UTC).isoformat())
        alerts = []
        for assignment in state.get("assignments", []):
            deadline = datetime.fromisoformat(assignment["deadline"])
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if deadline >= now:
                continue
            submitted = set(assignment.get("submitted_student_ids", []))
            for student_id in assignment.get("enrolled_student_ids", []):
                if student_id not in submitted:
                    alerts.append(
                        {
                            "kind": "missing",
                            "target_student_id": student_id,
                            "target_assignment_id": assignment["assignment_id"],
                            "payload": {
                                "title": assignment.get("title"),
                                "deadline": deadline.isoformat(),
                            },
                        }
                    )
        return {"alerts": alerts}

    def compute_submission_rates(state: MonitoringState) -> dict:
        alerts = []
        for assignment in state.get("scanned_deadlines", []):
            enrollment = int(assignment.get("enrollment_count", 0))
            submitted = int(assignment.get("submitted_count", 0))
            rate = submitted / enrollment if enrollment else 1.0
            if assignment.get("hours_left", 999) <= 24 and rate < 0.6:
                alerts.append(
                    {
                        "kind": "due_soon_low_rate",
                        "target_assignment_id": assignment["assignment_id"],
                        "payload": {
                            "submission_rate": rate,
                            "submitted": submitted,
                            "enrolled": enrollment,
                            "hours_left": assignment["hours_left"],
                        },
                    }
                )
        return {"alerts": alerts}

    def find_review_backlog(state: MonitoringState) -> dict:
        return {
            "alerts": [
                {
                    "kind": "overdue_review",
                    "target_assignment_id": row["assignment_id"],
                    "payload": {
                        "evaluation_id": row["evaluation_id"],
                        "days_waiting": row["days_waiting"],
                    },
                }
                for row in state.get("review_backlog", [])
                if float(row.get("days_waiting", 0)) > 3
            ]
        }

    def find_at_risk_students(state: MonitoringState) -> dict:
        return {
            "alerts": [
                {
                    "kind": "at_risk",
                    "target_student_id": row["student_id"],
                    "payload": row.get("payload", {}),
                }
                for row in state.get("at_risk_students", [])
                if row.get("at_risk")
            ]
        }

    def find_weak_topics(state: MonitoringState) -> dict:
        return {
            "alerts": [
                {
                    "kind": "weak_topic",
                    "topic_id": row["topic_id"],
                    "payload": {
                        "name": row.get("name"),
                        "below_fraction": row["below_fraction"],
                        "n": row["n"],
                    },
                }
                for row in state.get("weak_topics", [])
                if int(row.get("n", 0)) >= 8 and float(row.get("below_fraction", 0)) >= 0.4
            ]
        }

    def dedupe_alerts(state: MonitoringState) -> dict:
        existing = set(state.get("open_alert_keys", []))
        seen: set[tuple] = set()
        new_alerts = []
        for alert in state.get("alerts", []):
            key = alert_key(alert)
            if key in existing or key in seen:
                continue
            seen.add(key)
            new_alerts.append(alert)
        return {"new_alerts": new_alerts}

    def generate_digest(state: MonitoringState) -> dict:
        alerts = state.get("new_alerts", [])
        if not alerts:
            return {"digest": "No new alerts."}
        try:
            result = (
                llm_factory()
                .with_structured_output(MonitoringDigest)
                .invoke(
                    "Summarize only these new course monitoring alerts in 1-3 concise "
                    "faculty-facing "
                    f"sentences. Do not add facts or identify students by name. Alerts: {alerts}"
                )
            )
            return {"digest": result.digest, "digest_fallback": False}
        except Exception:
            # Alert persistence must not depend on an optional narrative summary.
            return {
                "digest": f"{len(alerts)} new monitoring alerts require review.",
                "digest_fallback": True,
            }

    builder = StateGraph(MonitoringState)
    builder.add_node("scan_deadlines", scan_deadlines)
    builder.add_node("find_missing_and_late", find_missing_and_late)
    builder.add_node("compute_submission_rates", compute_submission_rates)
    builder.add_node("find_review_backlog", find_review_backlog)
    builder.add_node("find_at_risk_students", find_at_risk_students)
    builder.add_node("find_weak_topics", find_weak_topics)
    builder.add_node("dedupe_alerts", dedupe_alerts)
    builder.add_node("generate_digest", generate_digest)
    builder.add_edge(START, "scan_deadlines")
    builder.add_edge("scan_deadlines", "find_missing_and_late")
    builder.add_edge("find_missing_and_late", "compute_submission_rates")
    builder.add_edge("compute_submission_rates", "find_review_backlog")
    builder.add_edge("find_review_backlog", "find_at_risk_students")
    builder.add_edge("find_at_risk_students", "find_weak_topics")
    builder.add_edge("find_weak_topics", "dedupe_alerts")
    builder.add_edge("dedupe_alerts", "generate_digest")
    builder.add_edge("generate_digest", END)
    return builder.compile(checkpointer=checkpointer)
