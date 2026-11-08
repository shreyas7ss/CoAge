"""Phase 3: submissions, submission_answers, evaluations, criterion_scores

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("file_uri", sa.String(length=512), nullable=True),
        sa.Column("ai_disclosure", sa.Text(), nullable=True),
        sa.Column("eval_thread_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
    )
    op.create_index(op.f("ix_submissions_assignment_id"), "submissions", ["assignment_id"])
    op.create_index(op.f("ix_submissions_student_id"), "submissions", ["student_id"])

    op.create_table(
        "submission_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
    )
    op.create_index(op.f("ix_submission_answers_submission_id"), "submission_answers", ["submission_id"])
    op.create_index(op.f("ix_submission_answers_question_id"), "submission_answers", ["question_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("ai_total", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("final_total", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("faculty_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
    )
    op.create_index(op.f("ix_evaluations_submission_id"), "evaluations", ["submission_id"])

    op.create_table(
        "criterion_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=True),
        sa.Column("ai_awarded", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("final_awarded", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_marks", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("matched_misconception", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("needs_manual", sa.Boolean(), nullable=False),
        sa.Column("faculty_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"]),
        sa.ForeignKeyConstraint(["criterion_id"], ["rubric_criteria.id"]),
    )
    op.create_index(op.f("ix_criterion_scores_evaluation_id"), "criterion_scores", ["evaluation_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_criterion_scores_evaluation_id"), table_name="criterion_scores")
    op.drop_table("criterion_scores")
    op.drop_index(op.f("ix_evaluations_submission_id"), table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index(op.f("ix_submission_answers_question_id"), table_name="submission_answers")
    op.drop_index(op.f("ix_submission_answers_submission_id"), table_name="submission_answers")
    op.drop_table("submission_answers")
    op.drop_index(op.f("ix_submissions_student_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_assignment_id"), table_name="submissions")
    op.drop_table("submissions")
