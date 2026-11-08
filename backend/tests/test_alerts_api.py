"""Alert routes enforce course ownership and expose deterministic monitoring runs."""

from datetime import UTC, datetime, timedelta

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.common import runner
from app.models.assignment import Assignment
from app.models.communication import Alert
from app.models.course import Course, Enrollment
from app.models.enums import UserRole
from app.schemas.llm import MonitoringDigest
from tests.fake_llm import FakeLLM
from tests.helpers import auth_header, make_user


def test_alert_list_resolve_and_manual_monitoring_are_faculty_scoped(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    other = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)
    course = Course(faculty_id=faculty.id, code="AL101", name="Alerts")
    db_session.add(course)
    db_session.flush()
    db_session.add(Enrollment(course_id=course.id, student_id=student.id))
    assignment = Assignment(
        course_id=course.id,
        title="Past due",
        deadline=datetime.now(UTC) - timedelta(days=1),
        max_marks=10,
        status="published",
    )
    db_session.add(assignment)
    db_session.commit()
    runner.configure_runtime(
        checkpointer=InMemorySaver(),
        llm_factory=lambda: FakeLLM(
            {MonitoringDigest: lambda: MonitoringDigest(digest="One missing.")}
        ),
    )

    manual = client.post(
        f"/api/v1/courses/{course.id}/monitoring/run", headers=auth_header(faculty)
    )
    assert manual.status_code == 202
    assert manual.json()["created"] == 1
    listed = client.get(f"/api/v1/courses/{course.id}/alerts", headers=auth_header(faculty))
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["kind"] == "missing"

    # A second run sees the open (kind, target) and does not recreate it.
    again = client.post(f"/api/v1/courses/{course.id}/monitoring/run", headers=auth_header(faculty))
    assert again.status_code == 202
    assert again.json()["created"] == 0
    alert = db_session.query(Alert).filter_by(course_id=course.id).one()

    resolved = client.post(f"/api/v1/alerts/{alert.id}/resolve", headers=auth_header(faculty))
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert (
        client.get(f"/api/v1/courses/{course.id}/alerts", headers=auth_header(other)).status_code
        == 403
    )
