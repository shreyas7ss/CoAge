"""Seed script v0 verification (runs against the SQLite test fixture)."""

from app.models.course import Course, Enrollment, Topic
from app.models.user import User
from scripts.seed import seed


def test_seed_creates_expected_rows(db_session) -> None:
    seed(db_session)
    assert db_session.query(User).count() == 16  # 1 faculty + 15 students
    assert db_session.query(Course).count() == 1
    assert db_session.query(Topic).count() == 8
    assert db_session.query(Enrollment).count() == 15


def test_seed_is_idempotent(db_session) -> None:
    seed(db_session)
    seed(db_session)
    assert db_session.query(User).count() == 16
    assert db_session.query(Course).count() == 1
