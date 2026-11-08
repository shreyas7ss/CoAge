"""Phase 2: assignments, questions, grading_packages, rubric_criteria

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allow_late", sa.Boolean(), nullable=False),
        sa.Column("late_penalty_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("max_marks", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("grade_weight", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("ai_policy", sa.String(length=32), nullable=False),
        sa.Column("require_understanding_check", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("active_package_version", sa.Integer(), nullable=True),
        sa.Column("setup_thread_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
    )
    op.create_index(op.f("ix_assignments_course_id"), "assignments", ["course_id"], unique=False)

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("qtype", sa.String(length=20), nullable=False),
        sa.Column("max_marks", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("mcq_options", sa.JSON(), nullable=True),
        sa.Column("mcq_correct", sa.JSON(), nullable=True),
        sa.Column("test_cases", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
    )
    op.create_index(op.f("ix_questions_assignment_id"), "questions", ["assignment_id"], unique=False)

    op.create_table(
        "grading_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.UniqueConstraint("assignment_id", "version", name="uq_package_assignment_version"),
    )
    op.create_index(
        op.f("ix_grading_packages_assignment_id"),
        "grading_packages",
        ["assignment_id"],
        unique=False,
    )

    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("marks", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("topic_weight", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
    )
    op.create_index(
        op.f("ix_rubric_criteria_question_id"), "rubric_criteria", ["question_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rubric_criteria_question_id"), table_name="rubric_criteria")
    op.drop_table("rubric_criteria")
    op.drop_index(op.f("ix_grading_packages_assignment_id"), table_name="grading_packages")
    op.drop_table("grading_packages")
    op.drop_index(op.f("ix_questions_assignment_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_assignments_course_id"), table_name="assignments")
    op.drop_table("assignments")
