"""Courses, topics, and enrollments router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    require_course_faculty,
    require_course_member,
    require_faculty,
)
from app.db.session import get_db
from app.models.course import Course, Enrollment, Topic
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.course import (
    CourseCreate,
    CourseRead,
    EnrollmentCreate,
    EnrollmentResult,
    TopicCreate,
    TopicRead,
    TopicUpdate,
)

router = APIRouter(tags=["courses"])


@router.get("/courses", response_model=list[CourseRead])
def list_courses(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Course]:
    if current_user.role == UserRole.faculty:
        return list(db.query(Course).filter(Course.faculty_id == current_user.id).all())
    return list(
        db.query(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(Enrollment.student_id == current_user.id)
        .all()
    )


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Course:
    course = Course(faculty_id=faculty.id, code=payload.code, name=payload.name, term=payload.term)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/courses/{course_id}/topics", response_model=list[TopicRead])
def list_topics(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Topic]:
    require_course_member(db, course_id, current_user)
    return list(db.query(Topic).filter(Topic.course_id == course_id).all())


@router.post(
    "/courses/{course_id}/topics", response_model=TopicRead, status_code=status.HTTP_201_CREATED
)
def create_topic(
    course_id: uuid.UUID,
    payload: TopicCreate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Topic:
    require_course_faculty(db, course_id, faculty)
    topic = Topic(
        course_id=course_id, name=payload.name, parent_id=payload.parent_id, weight=payload.weight
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.patch("/topics/{topic_id}", response_model=TopicRead)
def update_topic(
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    require_course_faculty(db, topic.course_id, faculty)
    if payload.name is not None:
        topic.name = payload.name
    if payload.parent_id is not None:
        topic.parent_id = payload.parent_id
    if payload.weight is not None:
        topic.weight = payload.weight
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> None:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    require_course_faculty(db, topic.course_id, faculty)
    db.delete(topic)
    db.commit()


@router.post("/courses/{course_id}/enrollments", response_model=EnrollmentResult)
def bulk_enroll(
    course_id: uuid.UUID,
    payload: EnrollmentCreate,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> EnrollmentResult:
    require_course_faculty(db, course_id, faculty)
    found: list[tuple[User, str]] = []
    not_found: list[str] = []

    for email in payload.emails or []:
        normalized = email.lower()
        student = (
            db.query(User).filter(User.email == normalized, User.role == UserRole.student).first()
        )
        if student is None:
            not_found.append(normalized)
        else:
            found.append((student, normalized))

    for roll_no in payload.roll_nos or []:
        student = (
            db.query(User).filter(User.roll_no == roll_no, User.role == UserRole.student).first()
        )
        if student is None:
            not_found.append(roll_no)
        else:
            found.append((student, roll_no))

    existing_ids = {
        e.student_id for e in db.query(Enrollment).filter(Enrollment.course_id == course_id).all()
    }
    enrolled: list[str] = []
    for student, label in found:
        if student.id not in existing_ids:
            db.add(Enrollment(course_id=course_id, student_id=student.id))
            existing_ids.add(student.id)
        enrolled.append(label)

    db.commit()
    return EnrollmentResult(enrolled=enrolled, not_found=not_found)
