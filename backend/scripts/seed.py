"""Seed v0: 1 faculty, 15 students, 1 course with 8 topics, all students enrolled.

Run from the backend directory:  python scripts/seed.py
(Assumes the schema exists via ``alembic upgrade head``.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.course import Course, Enrollment, Topic  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402

FACULTY_EMAIL = "faculty@example.com"
STUDENT_COUNT = 15
TOPICS = [
    "Introduction to Hashing",
    "Hash Functions",
    "Collision Resolution",
    "Open Addressing",
    "Chaining",
    "Load Factor and Rehashing",
    "Applications of Hashing",
    "Complexity Analysis",
]


def seed(db: Session) -> None:
    if db.query(User).filter(User.email == FACULTY_EMAIL).first() is not None:
        print("Seed already applied; skipping.")
        return

    faculty = User(
        email=FACULTY_EMAIL,
        password_hash=hash_password("faculty-pass"),
        full_name="Dr. Ada Lovelace",
        role=UserRole.faculty,
    )
    db.add(faculty)
    db.flush()

    course = Course(faculty_id=faculty.id, code="CS210", name="Data Structures", term="Fall 2026")
    db.add(course)
    db.flush()

    for name in TOPICS:
        db.add(Topic(course_id=course.id, name=name, weight=1.0))

    students = []
    for i in range(1, STUDENT_COUNT + 1):
        student = User(
            email=f"student{i}@example.com",
            password_hash=hash_password("student-pass"),
            full_name=f"Student {i}",
            role=UserRole.student,
            roll_no=f"R{i:03d}",
        )
        db.add(student)
        students.append(student)
    db.flush()

    for student in students:
        db.add(Enrollment(course_id=course.id, student_id=student.id))

    db.commit()
    print(f"Seeded 1 faculty, {len(students)} students, 1 course, {len(TOPICS)} topics.")


if __name__ == "__main__":
    seed(SessionLocal())
