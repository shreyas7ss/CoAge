"""Phase 6: correction memory and authenticity records.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "courses",
        sa.Column("process_logging_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("submission_answers", sa.Column("embedding", Vector(256), nullable=True))
    op.add_column("followup_checks", sa.Column("thread_id", sa.String(255), nullable=True))
    op.add_column(
        "followup_checks", sa.Column("retake_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "followup_checks", sa.Column("attempt_history", sa.JSON(), nullable=False, server_default="[]")
    )

    op.create_table(
        "authenticity_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("concern_level", sa.String(32), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("caveats", sa.JSON(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("baseline_updated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("faculty_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_authenticity_reports_submission_id", "authenticity_reports", ["submission_id"])

    op.create_table(
        "writing_baselines",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("n_samples", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("student_id"),
    )
    op.create_table(
        "process_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_events_submission_id", "process_events", ["submission_id"])

    op.create_table(
        "correction_memory",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("criterion_signature", sa.String(64), nullable=False),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("student_text_snippet", sa.Text(), nullable=False),
        sa.Column("ai_awarded", sa.Numeric(10, 4), nullable=False),
        sa.Column("final_awarded", sa.Numeric(10, 4), nullable=False),
        sa.Column("faculty_note", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_correction_memory_signature", "correction_memory", ["criterion_signature"]
    )


def downgrade() -> None:
    op.drop_index("ix_correction_memory_signature", table_name="correction_memory")
    op.drop_table("correction_memory")
    op.drop_index("ix_process_events_submission_id", table_name="process_events")
    op.drop_table("process_events")
    op.drop_table("writing_baselines")
    op.drop_index("ix_authenticity_reports_submission_id", table_name="authenticity_reports")
    op.drop_table("authenticity_reports")
    op.drop_column("followup_checks", "attempt_history")
    op.drop_column("followup_checks", "retake_count")
    op.drop_column("followup_checks", "thread_id")
    op.drop_column("submission_answers", "embedding")
    op.drop_column("courses", "process_logging_enabled")
