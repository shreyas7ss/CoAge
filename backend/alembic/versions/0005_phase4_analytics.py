"""Phase 4: topic mastery events and rollups.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_mastery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(10, 6), nullable=False),
        sa.Column("evidence_weight", sa.Numeric(10, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topic_mastery_events_student_id", "topic_mastery_events", ["student_id"])
    op.create_index("ix_topic_mastery_events_topic_id", "topic_mastery_events", ["topic_id"])
    op.create_index("ix_topic_mastery_events_submission_id", "topic_mastery_events", ["submission_id"])
    op.create_index("ix_topic_mastery_events_student_topic", "topic_mastery_events", ["student_id", "topic_id"])
    op.create_table(
        "topic_mastery",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("mastery", sa.Numeric(10, 6), nullable=False),
        sa.Column("confidence", sa.Numeric(10, 6), nullable=False),
        sa.Column("n_events", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("student_id", "topic_id"),
    )
    op.create_table(
        "followup_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("score", sa.Numeric(10, 6), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_limit_sec", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_followup_checks_submission_id", "followup_checks", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_followup_checks_submission_id", table_name="followup_checks")
    op.drop_table("followup_checks")
    op.drop_table("topic_mastery")
    op.drop_index("ix_topic_mastery_events_student_topic", table_name="topic_mastery_events")
    op.drop_index("ix_topic_mastery_events_submission_id", table_name="topic_mastery_events")
    op.drop_index("ix_topic_mastery_events_topic_id", table_name="topic_mastery_events")
    op.drop_index("ix_topic_mastery_events_student_id", table_name="topic_mastery_events")
    op.drop_table("topic_mastery_events")
