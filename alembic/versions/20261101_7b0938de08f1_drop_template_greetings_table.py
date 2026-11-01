"""drop template greetings table

Revision ID: 7b0938de08f1
Revises: d0a82d2914ab
Create Date: 2026-11-01 14:13:24.640258
"""

from __future__ import annotations

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = "7b0938de08f1"
down_revision: str | None = "d0a82d2914ab"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Drop the unused `greetings` table left over from the project template."""
    op.drop_table("greetings")


def downgrade() -> None:
    """Recreate `greetings` (id, user_name, message, created_at) as in revision 20260101_0001."""
    op.create_table(
        "greetings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_name", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
