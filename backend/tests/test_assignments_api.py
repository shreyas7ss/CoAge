"""Assignments API tests: RBAC, CRUD, and the setup-graph package flow."""

import uuid
from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.common import runner
from app.models.assignment import Assignment, Question
from app.models.course import Course, Enrollment, Topic
from app.models.enums import UserRole
from app.schemas.llm import DraftedCriterion, DraftedPackage, DraftedQuestion
from tests.fake_llm import FakeLLM, FakeLLMFactory
from tests.helpers import auth_header, make_user

DEADLINE = (datetime.now(UTC) + timedelta(days=7)).isoformat()


def _course(db, faculty) -> Course:
    course = Course(faculty_id=faculty.id, code="CS101", name="Data Structures")
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _topic(db, course, name: str = "Hashing") -> Topic:
    topic = Topic(course_id=course.id, name=name)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def _enroll(db, course_id, student_id) -> None:
    db.add(Enrollment(course_id=course_id, student_id=student_id))
    db.commit()


def _package(qid: str, topic_id: str) -> DraftedPackage:
    return DraftedPackage(
        questions=[
            DraftedQuestion(
                q_id=qid,
                reference_answer="A collision is when two keys map to the same slot.",
                rubric=[
                    DraftedCriterion(criterion="Defines a collision", marks=6, topic=topic_id),
                    DraftedCriterion(criterion="Explains chaining", marks=4, topic=topic_id),
                ],
            )
        ]
    )


def test_student_cannot_create_assignment(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    student = make_user(db_session, role=UserRole.student)
    resp = client.post(
        f"/api/v1/courses/{course.id}/assignments",
        json={"title": "A1", "deadline": DEADLINE, "max_marks": 10},
        headers=auth_header(student),
    )
    assert resp.status_code == 403


def test_student_cannot_access_package(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    student = make_user(db_session, role=UserRole.student)
    _enroll(db_session, course.id, student.id)
    assignment = Assignment(
        course_id=course.id,
        title="A1",
        deadline=datetime.now(UTC) + timedelta(days=1),
        max_marks=10,
        status="published",
    )
    db_session.add(assignment)
    db_session.commit()
    db_session.refresh(assignment)
    assert (
        client.get(
            f"/api/v1/assignments/{assignment.id}/package", headers=auth_header(student)
        ).status_code
        == 403
    )


def test_student_sees_only_published_assignments(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    student = make_user(db_session, role=UserRole.student)
    _enroll(db_session, course.id, student.id)
    db_session.add_all(
        [
            Assignment(
                course_id=course.id, title="Draft", deadline=datetime.now(UTC) + timedelta(days=1),
                max_marks=10, status="draft",
            ),
            Assignment(
                course_id=course.id, title="Published",
                deadline=datetime.now(UTC) + timedelta(days=2), max_marks=10, status="published",
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/v1/courses/{course.id}/assignments", headers=auth_header(student))
    assert resp.status_code == 200
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Published"]


def test_faculty_create_assignment_with_questions(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    resp = client.post(
        f"/api/v1/courses/{course.id}/assignments",
        json={
            "title": "A1",
            "deadline": DEADLINE,
            "max_marks": 10,
            "questions": [
                {
                    "position": 1,
                    "prompt": "Define a collision",
                    "qtype": "short_answer",
                    "max_marks": 10,
                }
            ],
        },
        headers=auth_header(faculty),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assignment_id = uuid.UUID(body["id"])
    assert db_session.query(Question).filter_by(assignment_id=assignment_id).count() == 1


def test_package_setup_flow_end_to_end(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    topic = _topic(db_session, course)
    headers = auth_header(faculty)

    create = client.post(
        f"/api/v1/courses/{course.id}/assignments",
        json={"title": "A1", "deadline": DEADLINE, "max_marks": 10},
        headers=headers,
    )
    assignment_id = create.json()["id"]

    qresp = client.post(
        f"/api/v1/assignments/{assignment_id}/questions",
        json={
            "questions": [
                {
                    "position": 1,
                    "prompt": "Define a collision",
                    "qtype": "short_answer",
                    "max_marks": 10,
                }
            ]
        },
        headers=headers,
    )
    question_id = qresp.json()[0]["id"]

    llm = FakeLLM({DraftedPackage: lambda: _package(question_id, str(topic.id))})
    runner.configure_runtime(checkpointer=InMemorySaver(), llm_factory=FakeLLMFactory(llm))

    start = client.post(f"/api/v1/assignments/{assignment_id}/package/start", headers=headers)
    assert start.status_code == 200
    assert start.json()["status"] == "interrupted"
    assert start.json()["package"] is not None

    decision = client.post(
        f"/api/v1/assignments/{assignment_id}/package/decision",
        json={"approved": True, "package": start.json()["package"]},
        headers=headers,
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "finished"
    assert decision.json()["package_version"] == 1

    packages = client.get(
        f"/api/v1/assignments/{assignment_id}/package", headers=headers
    ).json()
    assert [p["version"] for p in packages] == [1]
    assert all(p["status"] == "approved" for p in packages)
