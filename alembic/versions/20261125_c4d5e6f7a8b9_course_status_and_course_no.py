"""add courses.status, courses.course_no, and plural literature target_category default

Revision ID: c4d5e6f7a8b9
Revises: 85aedf6f2f6f
Create Date: 2026-11-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "85aedf6f2f6f"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add `status` and `course_no` to `courses` and set plural literature category default."""
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False)
        )
        batch_op.add_column(sa.Column("course_no", sa.String(length=50), server_default="", nullable=False))

    with op.batch_alter_table("literature_items", schema=None) as batch_op:
        batch_op.alter_column(
            "target_category",
            existing_type=sa.String(length=60),
            server_default="01 Materials",
            existing_nullable=False,
        )


def downgrade() -> None:
    """Revert `courses.status`, `courses.course_no`, and literature target_category default."""
    with op.batch_alter_table("literature_items", schema=None) as batch_op:
        batch_op.alter_column(
            "target_category",
            existing_type=sa.String(length=60),
            server_default="01 Material",
            existing_nullable=False,
        )

    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_column("course_no")
        batch_op.drop_column("status")
