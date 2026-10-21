"""Create the greetings table.

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create `greetings` (id, user_name, message, created_at)."""
    op.create_table(
        "greetings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_name", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop `greetings`."""
    op.drop_table("greetings")
