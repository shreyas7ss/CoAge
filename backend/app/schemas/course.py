"""Course, topic, and enrollment schemas."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    term: str | None = Field(default=None, max_length=64)


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    faculty_id: uuid.UUID
    code: str
    name: str
    term: str | None = None


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    weight: float = 1.0


class TopicUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    weight: float | None = None


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None = None
    weight: float


class EnrollmentCreate(BaseModel):
    emails: list[str] | None = None
    roll_nos: list[str] | None = None


class EnrollmentResult(BaseModel):
    enrolled: list[str] = []
    not_found: list[str] = []
