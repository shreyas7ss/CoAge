"""Phase 5: feedback and monitoring alerts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("feedback_draft", sa.Text(), nullable=True))
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("misconceptions", sa.JSON(), nullable=False),
        sa.Column("suggested_practice", sa.JSON(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_feedback_submission_id", "feedback", ["submission_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("target_student_id", sa.Uuid(), nullable=True),
        sa.Column("target_assignment_id", sa.Uuid(), nullable=True),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["target_student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("course_id", "kind", "target_student_id", "target_assignment_id", "topic_id", "status"):
        op.create_index(f"ix_alerts_{column}", "alerts", [column])


def downgrade() -> None:
    for column in ("status", "topic_id", "target_assignment_id", "target_student_id", "kind", "course_id"):
        op.drop_index(f"ix_alerts_{column}", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_feedback_submission_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_column("evaluations", "feedback_draft")
