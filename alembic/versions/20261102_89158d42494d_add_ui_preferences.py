"""Add the ui_preferences table: web preferences recorded on this computer (ADR-009).

Revision ID: 89158d42494d
Revises: b3bed90c05da
Create Date: 2026-11-02 15:34:25.329118
"""

from __future__ import annotations

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = "89158d42494d"
down_revision: str | None = "b3bed90c05da"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create ui_preferences (key, value text, updated_at)."""
    op.create_table(
        "ui_preferences",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop ui_preferences."""
    op.drop_table("ui_preferences")
