"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | None = ${repr(branch_labels)}
depends_on: str | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this revision (describe the schema change here)."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert this revision."""
    ${downgrades if downgrades else "pass"}
