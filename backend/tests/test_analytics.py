"""Analytics worked examples and faculty-only route coverage."""

import pytest

from app.analytics.metrics import (
    agreement_metrics,
    apply_late_penalty,
    below_threshold,
    difficulty_index,
    item_analysis,
    mastery_ema,
    mastery_trend,
    score_distribution,
    subject_understanding,
    topic_score,
    understanding_gap,
)
from app.models.course import Course, Enrollment, Topic
from app.models.enums import UserRole
from app.models.user import User
from tests.helpers import auth_header, make_user


def test_topic_score_worked_examples() -> None:
    criteria = [
        {"topic_id": "A", "final_awarded": 2, "max_marks": 2, "topic_weight": 1},
        {"topic_id": "A", "final_awarded": 3, "max_marks": 4, "topic_weight": 1},
    ]
    assert topic_score(criteria, "A") == pytest.approx(0.875)
    criteria[0]["topic_weight"] = 2
    assert topic_score(criteria, "A") == pytest.approx(0.9166666667)
    assert topic_score(criteria, "missing") is None


def test_mastery_subject_and_trend_examples() -> None:
    assert mastery_ema([0.60, 0.875, 0.50]) == pytest.approx(
        {"mastery": 0.626, "confidence": 0.6, "n_events": 3}
    )
    assert subject_understanding(
        [
            {"mastery": 0.71, "weight": 2},
            {"mastery": 0.50, "weight": 1},
            {"mastery": None, "weight": 1},
        ]
    ) == pytest.approx({"subject_pct": 0.64, "coverage": 2 / 3})
    trend = mastery_trend([0.60, 0.71, 0.626, 0.70])
    assert trend["change"] == pytest.approx(0.10)
    assert trend["label"] == "up"
    assert mastery_trend([0.6, 0.7]) == {"change": None, "label": "insufficient_data"}


def test_item_analysis_worked_examples() -> None:
    ratios = [1.0, 0.8, 0.6, 0.4, 0.2]
    assert difficulty_index(ratios) == pytest.approx(0.6)
    assert (
        item_analysis([{"ratio": value, "other_total": value} for value in ratios])["status"]
        == "insufficient_data"
    )
    values = [1.0, 0.8, 0.6, 0.4, 0.2] * 2
    rows = [{"ratio": value, "other_total": value * 10} for value in values]
    positive = item_analysis(rows)
    assert positive["difficulty"] == pytest.approx(0.6)
    assert positive["discrimination"] == pytest.approx(1.0)
    reverse = item_analysis(
        [{"ratio": row["ratio"], "other_total": 11 - row["other_total"]} for row in rows]
    )
    assert reverse["discrimination"] == pytest.approx(-1.0)


def test_weak_threshold_distribution_agreement_and_gap_examples() -> None:
    assert below_threshold([0.20, 0.30, 0.45, 0.49, 0.50, 0.55, 0.60, 0.70, 0.80, 0.90]) == {
        "below": 4,
        "n": 10,
        "fraction": 0.4,
    }
    assert score_distribution([0.2, 0.5, 1.0])["n"] == 3
    assert agreement_metrics(
        [
            {"ai_awarded": ai, "final_awarded": final, "max_marks": 5, "confidence": 0.9}
            for ai, final in zip([4, 3, 2, 5], [4, 2, 2, 5], strict=True)
        ]
    ) == {
        "n": 4,
        "agreement_rate": 0.75,
        "within_5pct_rate": 0.75,
        "mae": 0.05,
        "override_rate": 0.25,
        "calibration": [
            {"from": 0, "to": 0.5, "n": 0, "agreement_rate": None},
            {"from": 0.5, "to": 0.7, "n": 0, "agreement_rate": None},
            {"from": 0.7, "to": 0.85, "n": 0, "agreement_rate": None},
            {"from": 0.85, "to": 1.0, "n": 4, "agreement_rate": 0.75},
        ],
    }
    assert understanding_gap(0.85, 0.40) == pytest.approx(0.45)
    assert apply_late_penalty(18, 10) == 16.2


def _course(db, faculty: User) -> Course:
    course = Course(faculty_id=faculty.id, code="AN101", name="Analytics")
    db.add(course)
    db.flush()
    topic = Topic(course_id=course.id, name="Foundations")
    student = make_user(db, role=UserRole.student)
    db.add(topic)
    db.add(Enrollment(course_id=course.id, student_id=student.id))
    db.commit()
    return course


def test_analytics_routes_are_faculty_only_and_course_scoped(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    other_faculty = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)

    response = client.get(
        f"/api/v1/courses/{course.id}/analytics/heatmap", headers=auth_header(faculty)
    )
    assert response.status_code == 200
    assert response.json()["cells"] == []
    assert (
        client.get(
            f"/api/v1/courses/{course.id}/analytics/students", headers=auth_header(student)
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/courses/{course.id}/analytics/topics", headers=auth_header(other_faculty)
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/courses/{course.id}/analytics/students", headers=auth_header(faculty)
        ).json()["students"][0]["coverage"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/courses/{course.id}/analytics/distribution", headers=auth_header(faculty)
        ).json()["n"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/courses/{course.id}/analytics/understanding-gap",
            headers=auth_header(faculty),
        ).json()["available"]
        is False
    )
