"""FastAPI auth dependencies and role-based access control helpers."""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.course import Course, Enrollment
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError as err:
        raise _credentials_error() from err
    sub = payload.get("sub")
    if sub is None:
        raise _credentials_error()
    try:
        user_id = uuid.UUID(sub)
    except ValueError as err:
        raise _credentials_error() from err
    user = db.get(User, user_id)
    if user is None:
        raise _credentials_error()
    return user


def require_faculty(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.faculty:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty access required")
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required")
    return current_user


def get_course_or_404(db: Session, course_id: uuid.UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def require_course_faculty(db: Session, course_id: uuid.UUID, faculty: User) -> Course:
    """Faculty must own the course."""
    course = get_course_or_404(db, course_id)
    if course.faculty_id != faculty.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your course")
    return course


def require_course_member(db: Session, course_id: uuid.UUID, user: User) -> Course:
    """Faculty must own the course; students must be enrolled."""
    course = get_course_or_404(db, course_id)
    if user.role == UserRole.faculty:
        if course.faculty_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your course")
        return course
    enrollment = db.query(Enrollment).filter_by(course_id=course_id, student_id=user.id).first()
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course"
        )
    return course
