"""Phase 1: users, courses, enrollments, topics

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("roll_no", sa.String(length=64), nullable=True),
        sa.Column("native_english", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("faculty_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("term", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["faculty_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_courses_faculty_id"), "courses", ["faculty_id"], unique=False)

    op.create_table(
        "enrollments",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("course_id", "student_id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["topics.id"]),
    )
    op.create_index(op.f("ix_topics_course_id"), "topics", ["course_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_topics_course_id"), table_name="topics")
    op.drop_table("topics")
    op.drop_table("enrollments")
    op.drop_index(op.f("ix_courses_faculty_id"), table_name="courses")
    op.drop_table("courses")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
