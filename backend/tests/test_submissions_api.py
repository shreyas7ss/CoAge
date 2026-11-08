"""Submission API tests: full evaluation flow + RBAC."""

import uuid
from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.common import runner
from app.models.analytics import TopicMastery, TopicMasteryEvent
from app.models.assignment import Assignment, Question
from app.models.course import Course, Enrollment, Topic
from app.models.enums import EvalStatus, SubmissionStatus, UserRole
from app.models.submission import Evaluation, Submission
from app.schemas.llm import CriterionResult, FeedbackDraft
from app.services import setup_service
from tests.fake_llm import FakeLLM, FakeLLMFactory
from tests.helpers import auth_header, make_user


def _faculty_and_course(db):
    faculty = make_user(db, role=UserRole.faculty)
    course = Course(faculty_id=faculty.id, code="CS101", name="Data Structures")
    db.add(course)
    db.commit()
    db.refresh(course)
    return faculty, course


def _topic(db, course):
    topic = Topic(course_id=course.id, name="Hashing")
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def _assignment(db, course, status="published"):
    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        deadline=datetime.now(UTC) + timedelta(days=7),
        max_marks=10.0,
        status=status,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def _published_assignment_with_package(db, faculty):
    course = Course(faculty_id=faculty.id, code="CS101", name="Data Structures")
    db.add(course)
    db.flush()
    topic = Topic(course_id=course.id, name="Hashing")
    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        deadline=datetime.now(UTC) + timedelta(days=7),
        max_marks=10.0,
    )
    db.add(assignment)
    db.flush()
    question = Question(
        assignment_id=assignment.id,
        position=1,
        prompt="Define a collision.",
        qtype="short_answer",
        max_marks=10.0,
    )
    db.add_all([topic, question])
    db.commit()
    db.refresh(assignment)
    db.refresh(question)
    package = {
        "questions": [
            {
                "q_id": str(question.id),
                "reference_answer": "A collision is when two keys map to the same slot.",
                "rubric": [
                    {"criterion": "Defines collision", "marks": 6, "topic": str(topic.id)},
                    {"criterion": "Explains chaining", "marks": 4, "topic": str(topic.id)},
                ],
            }
        ]
    }
    setup_service.lock_package(db, assignment, package, faculty.id)
    assignment.status = "published"
    db.commit()
    db.refresh(assignment)
    return course, topic, assignment, question


def _configure_fake_runtime() -> None:
    llm = FakeLLM(
        {
            CriterionResult: lambda: CriterionResult(awarded=3.0, evidence="quote", confidence=0.9),
            FeedbackDraft: lambda: FeedbackDraft(rationale="r", feedback="f"),
        }
    )
    runner.configure_runtime(checkpointer=InMemorySaver(), llm_factory=FakeLLMFactory(llm))


def test_full_submission_flow(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course, topic, assignment, _ = _published_assignment_with_package(db_session, faculty)
    student = make_user(db_session, role=UserRole.student)
    db_session.add(Enrollment(course_id=course.id, student_id=student.id))
    db_session.commit()
    _configure_fake_runtime()

    student_headers = auth_header(student)
    faculty_headers = auth_header(faculty)

    resp = client.post(
        f"/api/v1/assignments/{assignment.id}/submissions",
        data={"text": "A collision is when two keys map to the same slot."},
        headers=student_headers,
    )
    assert resp.status_code == 201
    submission_id = uuid.UUID(resp.json()["id"])
    # Submission creation returns before the post-response evaluation job runs.
    assert resp.json()["status"] == "submitted"

    queue = client.get(f"/api/v1/courses/{course.id}/review-queue", headers=faculty_headers)
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    evaluation_id = queue.json()[0]["id"]

    detail = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=faculty_headers)
    assert detail.status_code == 200
    assert detail.json()["ai_total"] == 6.0
    assert len(detail.json()["criterion_scores"]) == 2

    decision = client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision",
        json={"approve": True, "final_scores": {}},
        headers=faculty_headers,
    )
    assert decision.status_code == 200
    assert decision.json()["evaluation_status"] == "approved"
    submission = db_session.get(Submission, submission_id)
    mastery_event = (
        db_session.query(TopicMasteryEvent)
        .filter_by(student_id=submission.student_id, topic_id=topic.id)
        .one()
    )
    assert float(mastery_event.score) == 0.625
    assert (
        db_session.query(TopicMastery)
        .filter_by(student_id=mastery_event.student_id, topic_id=mastery_event.topic_id)
        .one()
        .n_events
        == 1
    )

    my_sub = client.get(
        f"/api/v1/assignments/{assignment.id}/my-submission", headers=student_headers
    )
    assert my_sub.json()["status"] == "graded"

    release = client.post(f"/api/v1/evaluations/{evaluation_id}/release", headers=faculty_headers)
    assert release.status_code == 200

    result = client.get(f"/api/v1/submissions/{submission_id}/result", headers=student_headers)
    assert result.status_code == 200
    assert result.json()["total"] == 6.0


def test_student_cannot_access_review_queue(client, db_session) -> None:
    faculty, course = _faculty_and_course(db_session)
    student = make_user(db_session, role=UserRole.student)
    resp = client.get(f"/api/v1/courses/{course.id}/review-queue", headers=auth_header(student))
    assert resp.status_code == 403


def test_student_cannot_list_submissions(client, db_session) -> None:
    faculty, course = _faculty_and_course(db_session)
    assignment = _assignment(db_session, course)
    student = make_user(db_session, role=UserRole.student)
    resp = client.get(
        f"/api/v1/assignments/{assignment.id}/submissions", headers=auth_header(student)
    )
    assert resp.status_code == 403


def test_student_cannot_access_evaluation_detail(client, db_session) -> None:
    faculty, course = _faculty_and_course(db_session)
    assignment = _assignment(db_session, course)
    student = make_user(db_session, role=UserRole.student)
    submission = Submission(
        assignment_id=assignment.id, student_id=student.id, status=SubmissionStatus.pending_review
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)
    evaluation = Evaluation(
        submission_id=submission.id, package_version=1, status=EvalStatus.awaiting_review
    )
    db_session.add(evaluation)
    db_session.commit()
    db_session.refresh(evaluation)

    resp = client.get(f"/api/v1/evaluations/{evaluation.id}", headers=auth_header(student))
    assert resp.status_code == 403


def test_result_requires_release(client, db_session) -> None:
    faculty, course = _faculty_and_course(db_session)
    assignment = _assignment(db_session, course)
    student = make_user(db_session, role=UserRole.student)
    submission = Submission(
        assignment_id=assignment.id, student_id=student.id, status=SubmissionStatus.graded
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)
    evaluation = Evaluation(
        submission_id=submission.id, package_version=1, status=EvalStatus.approved, final_total=6.0
    )
    db_session.add(evaluation)
    db_session.commit()

    # Not released yet -> 403.
    assert (
        client.get(
            f"/api/v1/submissions/{submission.id}/result", headers=auth_header(student)
        ).status_code
        == 403
    )
    evaluation.released_at = datetime.now(UTC)
    db_session.commit()
    resp = client.get(f"/api/v1/submissions/{submission.id}/result", headers=auth_header(student))
    assert resp.status_code == 200
    assert resp.json()["total"] == 6.0


def test_student_cannot_see_other_students_result(client, db_session) -> None:
    faculty, course = _faculty_and_course(db_session)
    assignment = _assignment(db_session, course)
    student_a = make_user(db_session, role=UserRole.student)
    student_b = make_user(db_session, role=UserRole.student)
    submission = Submission(
        assignment_id=assignment.id, student_id=student_a.id, status=SubmissionStatus.graded
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)
    evaluation = Evaluation(
        submission_id=submission.id,
        package_version=1,
        status=EvalStatus.approved,
        final_total=6.0,
        released_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    db_session.commit()

    resp = client.get(f"/api/v1/submissions/{submission.id}/result", headers=auth_header(student_b))
    assert resp.status_code == 404
