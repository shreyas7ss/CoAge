"""Add classroom join codes and course study materials.

Revision ID: 0008
Revises: 0007
"""

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("join_code", sa.String(length=12), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM courses")).fetchall()
    for (course_id,) in rows:
        bind.execute(
            sa.text("UPDATE courses SET join_code = :code WHERE id = :id"),
            {"code": secrets.token_urlsafe(6)[:8].upper(), "id": course_id},
        )
    op.alter_column("courses", "join_code", nullable=False)
    op.create_index("ix_courses_join_code", "courses", ["join_code"], unique=True)
    op.create_table(
        "study_materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_materials_course_id", "study_materials", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_study_materials_course_id", table_name="study_materials")
    op.drop_table("study_materials")
    op.drop_index("ix_courses_join_code", table_name="courses")
    op.drop_column("courses", "join_code")
