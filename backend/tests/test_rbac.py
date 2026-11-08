"""RBAC test matrix for Phase 1 (auth, roles, courses, topics, enrollments)."""

from sqlalchemy.orm import Session

from app.models.course import Course, Enrollment, Topic
from app.models.enums import UserRole
from app.models.user import User
from tests.helpers import auth_header, make_user


def _make_course(db: Session, faculty: User, code: str = "CS101", name: str = "Course") -> Course:
    course = Course(faculty_id=faculty.id, code=code, name=name)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _enroll(db: Session, course_id, student_id) -> None:
    db.add(Enrollment(course_id=course_id, student_id=student_id))
    db.commit()


def test_unauthenticated_is_401(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    course = _make_course(db_session, faculty)

    assert client.get("/api/v1/courses").status_code == 401
    assert client.post("/api/v1/courses", json={"code": "X", "name": "Y"}).status_code == 401
    assert client.get(f"/api/v1/courses/{course.id}/topics").status_code == 401


def test_student_cannot_create_course(client, db_session) -> None:
    student = make_user(db_session, role=UserRole.student)
    resp = client.post(
        "/api/v1/courses", json={"code": "X", "name": "Y"}, headers=auth_header(student)
    )
    assert resp.status_code == 403


def test_student_cannot_manage_topics(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)
    course = _make_course(db_session, faculty)
    topic = Topic(course_id=course.id, name="T")
    db_session.add(topic)
    db_session.commit()
    db_session.refresh(topic)

    headers = auth_header(student)
    assert (
        client.post(
            f"/api/v1/courses/{course.id}/topics", json={"name": "X"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/topics/{topic.id}", json={"name": "X"}, headers=headers).status_code
        == 403
    )
    assert client.delete(f"/api/v1/topics/{topic.id}", headers=headers).status_code == 403


def test_student_cannot_enroll_others(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)
    course = _make_course(db_session, faculty)
    resp = client.post(
        f"/api/v1/courses/{course.id}/enrollments",
        json={"emails": ["a@b.com"]},
        headers=auth_header(student),
    )
    assert resp.status_code == 403


def test_student_sees_only_enrolled_courses(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    student_a = make_user(db_session, role=UserRole.student, email="a@example.com")
    student_b = make_user(db_session, role=UserRole.student, email="b@example.com")
    course1 = _make_course(db_session, faculty, code="C1", name="One")
    course2 = _make_course(db_session, faculty, code="C2", name="Two")
    _enroll(db_session, course1.id, student_a.id)
    _enroll(db_session, course2.id, student_b.id)

    resp = client.get("/api/v1/courses", headers=auth_header(student_a))
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()]
    assert codes == ["C1"]

    # student A must not read student B's course (not enrolled)
    resp = client.get(f"/api/v1/courses/{course2.id}/topics", headers=auth_header(student_a))
    assert resp.status_code == 403


def test_student_cannot_read_unenrolled_course_topics(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)
    course = _make_course(db_session, faculty)
    resp = client.get(f"/api/v1/courses/{course.id}/topics", headers=auth_header(student))
    assert resp.status_code == 403


def test_faculty_sees_only_owned_courses(client, db_session) -> None:
    f1 = make_user(db_session, role=UserRole.faculty, email="f1@example.com")
    f2 = make_user(db_session, role=UserRole.faculty, email="f2@example.com")
    _make_course(db_session, f1, code="F1", name="One")
    _make_course(db_session, f2, code="F2", name="Two")

    resp = client.get("/api/v1/courses", headers=auth_header(f1))
    codes = [c["code"] for c in resp.json()]
    assert codes == ["F1"]


def test_faculty_cannot_access_other_faculty_course(client, db_session) -> None:
    f1 = make_user(db_session, role=UserRole.faculty, email="f1@example.com")
    f2 = make_user(db_session, role=UserRole.faculty, email="f2@example.com")
    course2 = _make_course(db_session, f2, code="F2", name="Two")

    resp = client.get(f"/api/v1/courses/{course2.id}/topics", headers=auth_header(f1))
    assert resp.status_code == 403


def test_enrolled_student_can_read_topics(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    student = make_user(db_session, role=UserRole.student)
    course = _make_course(db_session, faculty)
    _enroll(db_session, course.id, student.id)
    db_session.add(Topic(course_id=course.id, name="Hashing"))
    db_session.commit()

    resp = client.get(f"/api/v1/courses/{course.id}/topics", headers=auth_header(student))
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Hashing"


def test_faculty_bulk_enroll_by_email_and_roll_no(client, db_session) -> None:
    faculty = make_user(db_session, role=UserRole.faculty)
    make_user(db_session, role=UserRole.student, email="s1@example.com", roll_no="R1")
    course = _make_course(db_session, faculty)

    resp = client.post(
        f"/api/v1/courses/{course.id}/enrollments",
        json={
            "emails": ["s1@example.com", "missing@example.com"],
            "roll_nos": ["R1", "R999"],
        },
        headers=auth_header(faculty),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "s1@example.com" in body["enrolled"]
    assert "R1" in body["enrolled"]
    assert "missing@example.com" in body["not_found"]
    assert "R999" in body["not_found"]

    count = db_session.query(Enrollment).filter(Enrollment.course_id == course.id).count()
    assert count == 1
