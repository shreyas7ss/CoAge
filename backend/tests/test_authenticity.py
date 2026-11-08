"""Authenticity calculations, follow-up flow, and faculty/student boundaries."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.authenticity.signals import (
    concern_level,
    cosine_similarity,
    hashing_embedding,
    style_drift,
    style_features,
    trigram_jaccard,
)
from app.agents.common import runner
from app.models.analytics import FollowupCheck
from app.models.assignment import Assignment, GradingPackage, Question
from app.models.course import Course, Enrollment, Topic
from app.models.enums import SubmissionStatus, UserRole
from app.models.submission import Submission, SubmissionAnswer
from app.schemas.llm import FollowupQuestionSet, FollowupScore
from tests.fake_llm import FakeLLM
from tests.helpers import auth_header, make_user


def test_style_features_and_baseline_drift() -> None:
    familiar = "The method works with the data and it is useful. We can test it, and then " * 30
    baseline = style_features(familiar)
    baseline_stats = {name: {"mean": value, "std": 0.1} for name, value in baseline.items()}
    assert style_drift(baseline, baseline_stats) == 0
    unusual = (
        "Consequently, notwithstanding the implementation, extraordinarily different "
        "terminology appears; " * 30
    )
    assert style_drift(style_features(unusual), baseline_stats) > 2


def test_similarity_embeddings_and_concern_levels() -> None:
    original = "A hash table stores values by mapping each key to an index using a hash function."
    near_copy = "A hash table stores values by mapping each key to an index using a hash function."
    assert cosine_similarity(
        hashing_embedding(original), hashing_embedding(near_copy)
    ) == pytest.approx(1)
    assert trigram_jaccard(original, near_copy) == 1
    cases = [
        ([], False, "insufficient_evidence"),
        ([{"status": "neutral"}, {"status": "neutral"}], False, "low"),
        ([{"status": "raised", "weight": 3}, {"status": "neutral"}], False, "medium"),
        ([{"status": "raised", "weight": 3}, {"status": "raised", "weight": 3}], False, "high"),
        (
            [
                {"status": "neutral"},
                {"status": "raised", "weight": 3},
                {"status": "raised", "weight": 3},
            ],
            True,
            "medium",
        ),
    ]
    for signals, passed, expected in cases:
        assert concern_level(signals, followup_passed=passed) == expected


def _followup_fixture(db):
    faculty = make_user(db, role=UserRole.faculty)
    student = make_user(db, role=UserRole.student)
    course = Course(
        faculty_id=faculty.id, code="AUTH1", name="Authenticity", process_logging_enabled=False
    )
    db.add(course)
    db.flush()
    topic = Topic(course_id=course.id, name="Hash Tables")
    assignment = Assignment(
        course_id=course.id,
        title="Hashing",
        deadline=datetime.now(UTC) + timedelta(days=1),
        max_marks=10,
        active_package_version=1,
        status="published",
        require_understanding_check=True,
    )
    db.add_all([topic, assignment])
    db.flush()
    question = Question(
        assignment_id=assignment.id,
        position=1,
        prompt="Explain a hash collision.",
        qtype="short_answer",
        max_marks=10,
    )
    db.add(question)
    db.flush()
    db.add(
        GradingPackage(
            assignment_id=assignment.id,
            version=1,
            status="approved",
            content={
                "questions": [
                    {
                        "q_id": str(question.id),
                        "reference_answer": (
                            "A collision maps multiple distinct keys to one table index."
                        ),
                    }
                ]
            },
        )
    )
    submission = Submission(
        assignment_id=assignment.id,
        student_id=student.id,
        status=SubmissionStatus.graded,
        submitted_at=datetime.now(UTC),
    )
    db.add(submission)
    db.add(Enrollment(course_id=course.id, student_id=student.id))
    db.flush()
    answer = "A collision happens when different keys map to the same slot in a hash table. " * 6
    db.add(
        SubmissionAnswer(
            submission_id=submission.id,
            question_id=question.id,
            answer_text=answer,
            embedding=hashing_embedding(answer),
        )
    )
    db.commit()
    return faculty, student, course, assignment, submission


def test_followup_interrupt_resume_retake_and_process_consent(client, db_session) -> None:
    faculty, student, course, _assignment, submission = _followup_fixture(db_session)
    peer = make_user(db_session, role=UserRole.student)
    runner.configure_runtime(
        checkpointer=InMemorySaver(),
        llm_factory=lambda: FakeLLM(
            {
                FollowupQuestionSet: lambda: FollowupQuestionSet(
                    questions=[
                        "Why do two keys sometimes share an index?",
                        "How can chaining handle that situation?",
                    ]
                ),
                FollowupScore: lambda: FollowupScore(
                    score=0.85, reasoning="Explains the idea correctly."
                ),
            }
        ),
    )

    requested = client.post(
        f"/api/v1/submissions/{submission.id}/authenticity/request-check",
        headers=auth_header(faculty),
    )
    assert requested.status_code == 202
    followup_id = requested.json()["followup_id"]
    assert len(requested.json()["questions"]) == 2
    assert (
        client.get("/api/v1/me/followups", headers=auth_header(student)).json()[0]["id"]
        == followup_id
    )
    assert (
        client.post(
            f"/api/v1/followups/{followup_id}/answers",
            json={
                "answers": [
                    "One index can be shared.",
                    "Chaining stores multiple values at that index.",
                ]
            },
            headers=auth_header(peer),
        ).status_code
        == 404
    )

    answered = client.post(
        f"/api/v1/followups/{followup_id}/answers",
        json={
            "answers": [
                "One index can be shared.",
                "Chaining stores multiple values at that index.",
            ]
        },
        headers=auth_header(student),
    )
    assert answered.status_code == 202
    assert float(answered.json()["score"]) == pytest.approx(0.85)
    report = client.get(
        f"/api/v1/submissions/{submission.id}/authenticity", headers=auth_header(faculty)
    )
    assert report.status_code == 200
    assert (
        next(signal for signal in report.json()["signals"] if signal["id"] == "S1")["status"]
        == "neutral"
    )
    assert (
        client.get(
            f"/api/v1/submissions/{submission.id}/authenticity", headers=auth_header(student)
        ).status_code
        == 403
    )

    retake = client.post(f"/api/v1/followups/{followup_id}/retake", headers=auth_header(student))
    assert retake.status_code == 202
    assert (
        client.post(
            f"/api/v1/followups/{followup_id}/answers",
            json={"answers": ["Keys share an index.", "Chaining stores them together."]},
            headers=auth_header(student),
        ).status_code
        == 202
    )
    assert (
        client.post(
            f"/api/v1/followups/{followup_id}/retake", headers=auth_header(student)
        ).status_code
        == 409
    )
    check = db_session.get(FollowupCheck, uuid.UUID(followup_id))
    assert check.retake_count == 1
    assert len(check.attempt_history) == 1

    assert (
        client.post(
            f"/api/v1/courses/{course.id}/process-logging",
            json={"enabled": True},
            headers=auth_header(faculty),
        ).json()["enabled"]
        is True
    )
    event = client.post(
        f"/api/v1/submissions/{submission.id}/process-events",
        json={"kind": "paste", "count": 1, "meta": {"paste_size_pct": 0.8}},
        headers=auth_header(student),
    )
    assert event.status_code == 201
    report = client.get(
        f"/api/v1/submissions/{submission.id}/authenticity", headers=auth_header(faculty)
    ).json()
    assert (
        next(signal for signal in report["signals"] if signal["id"] == "S3")["status"] == "raised"
    )
    forbidden_content = client.post(
        f"/api/v1/submissions/{submission.id}/process-events",
        json={"kind": "paste", "count": 1, "meta": {"paste_size_pct": 0.8}, "text": "secret"},
        headers=auth_header(student),
    )
    assert forbidden_content.status_code == 422
