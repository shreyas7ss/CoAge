"""Setup service tests: package locking/versioning and the runner integration."""

from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.common import runner
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.course import Course, Topic
from app.models.enums import UserRole
from app.schemas.llm import DraftedCriterion, DraftedPackage, DraftedQuestion
from app.services import setup_service
from tests.fake_llm import FakeLLM, FakeLLMFactory
from tests.helpers import make_user


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


def _assignment(db, course, max_marks: float = 10.0) -> Assignment:
    assignment = Assignment(
        course_id=course.id,
        title="Assignment 1",
        deadline=datetime.now(UTC) + timedelta(days=7),
        max_marks=max_marks,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def _question(db, assignment, max_marks: float = 10.0) -> Question:
    question = Question(
        assignment_id=assignment.id,
        position=1,
        prompt="Define a hash collision.",
        qtype="short_answer",
        max_marks=max_marks,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def _package(qid: str, topic_id: str, marks=(6.0, 4.0)) -> DraftedPackage:
    return DraftedPackage(
        questions=[
            DraftedQuestion(
                q_id=qid,
                reference_answer="A collision is when two keys map to the same slot.",
                common_misconceptions=["Thinks collisions mean data loss"],
                rubric=[
                    DraftedCriterion(
                        criterion="Defines a collision", marks=marks[0], topic=topic_id
                    ),
                    DraftedCriterion(criterion="Explains chaining", marks=marks[1], topic=topic_id),
                ],
            )
        ]
    )


def test_lock_package_creates_v1_and_copies_criteria(db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    topic = _topic(db_session, course)
    assignment = _assignment(db_session, course)
    question = _question(db_session, assignment)

    package = {
        "questions": [
            {
                "q_id": str(question.id),
                "reference_answer": "x",
                "rubric": [
                    {"criterion": "c1", "marks": 6, "topic": str(topic.id)},
                    {"criterion": "c2", "marks": 4, "topic": str(topic.id)},
                ],
            }
        ]
    }
    pkg = setup_service.lock_package(db_session, assignment, package, faculty.id)
    db_session.commit()

    assert pkg.version == 1
    assert pkg.status == "approved"
    assert assignment.active_package_version == 1
    criteria = db_session.query(RubricCriterion).filter_by(package_version=1).all()
    assert len(criteria) == 2
    assert {c.topic_id for c in criteria} == {topic.id}


def test_lock_package_twice_creates_v2_and_keeps_v1(db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    topic = _topic(db_session, course)
    assignment = _assignment(db_session, course)
    question = _question(db_session, assignment)

    def package_with(criteria):
        return {"questions": [{"q_id": str(question.id), "rubric": criteria}]}

    setup_service.lock_package(
        db_session,
        assignment,
        package_with([{"criterion": "c1", "marks": 10, "topic": str(topic.id)}]),
        faculty.id,
    )
    db_session.commit()

    setup_service.lock_package(
        db_session,
        assignment,
        package_with(
            [
                {"criterion": "c1", "marks": 5, "topic": str(topic.id)},
                {"criterion": "c2", "marks": 5, "topic": str(topic.id)},
            ]
        ),
        faculty.id,
    )
    db_session.commit()

    versions = {
        p.version
        for p in db_session.query(GradingPackage).filter_by(assignment_id=assignment.id).all()
    }
    assert versions == {1, 2}
    assert assignment.active_package_version == 2
    # v1 is immutable: still exactly one criterion.
    assert db_session.query(RubricCriterion).filter_by(package_version=1).count() == 1


def test_full_setup_flow_via_runner(db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _course(db_session, faculty)
    topic = _topic(db_session, course)
    assignment = _assignment(db_session, course)
    question = _question(db_session, assignment)

    llm = FakeLLM({DraftedPackage: lambda: _package(str(question.id), str(topic.id))})
    runner.configure_runtime(checkpointer=InMemorySaver(), llm_factory=FakeLLMFactory(llm))

    result = setup_service.start_setup(db_session, assignment)
    assert result["status"] == "interrupted"
    assert assignment.setup_thread_id == f"setup-{assignment.id}"

    draft = (
        db_session.query(GradingPackage).filter_by(assignment_id=assignment.id, version=0).first()
    )
    assert draft is not None and draft.status == "draft"

    payload = result["interrupt"][0]
    decision = {"approved": True, "package": payload["package"]}
    result2 = setup_service.resume_setup(db_session, assignment, decision, faculty.id)

    assert result2["status"] == "finished"
    assert assignment.active_package_version == 1
    assert (
        db_session.query(GradingPackage).filter_by(assignment_id=assignment.id, version=0).first()
        is None
    )
    assert db_session.query(RubricCriterion).filter_by(package_version=1).count() == 2
