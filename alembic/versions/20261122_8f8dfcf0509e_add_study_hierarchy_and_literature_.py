"""add study hierarchy and literature tables

Revision ID: 8f8dfcf0509e
Revises: 393ba6cc4afd
Create Date: 2026-11-22 22:13:53.167857
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = "8f8dfcf0509e"
down_revision: str | None = "393ba6cc4afd"
branch_labels: str | None = None
depends_on: str | None = None


def _create_literature_jobs() -> None:
    """Create the `literature_jobs` table (background fetch / identify / review jobs)."""
    op.create_table(
        "literature_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("started_at", sa.String(length=64), nullable=False),
        sa.Column("finished_at", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def _literature_item_reference_columns() -> list[sa.Column[Any]]:
    """Columns describing the tracked reference itself (input, APA, bibliographic fields).

    Returns:
        Column definitions in table order.
    """
    return [
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("apa", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("doi", sa.String(length=200), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("year", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("journal", sa.String(length=300), nullable=False),
        sa.Column("volume", sa.String(length=40), nullable=False),
        sa.Column("issue", sa.String(length=40), nullable=False),
        sa.Column("pages", sa.String(length=60), nullable=False),
        sa.Column("publisher", sa.String(length=300), nullable=False),
    ]


def _literature_item_tracking_columns() -> list[sa.Column[Any]]:
    """Columns tracking the downloaded file, its source, and where it is filed.

    Returns:
        Column definitions in table order.
    """
    return [
        sa.Column("file", sa.String(length=500), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("check_note", sa.Text(), nullable=False),
        sa.Column("course_code", sa.String(length=50), nullable=True),
        sa.Column("target_category", sa.String(length=60), server_default="01 Material", nullable=False),
        sa.Column(
            "target_subfolder", sa.String(length=255), server_default="Literature_Review", nullable=False
        ),
        sa.Column("imported_to_course", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _create_literature_items() -> None:
    """Create the `literature_items` table and its indexes."""
    op.create_table(
        "literature_items",
        *_literature_item_reference_columns(),
        *_literature_item_tracking_columns(),
        sa.ForeignKeyConstraint(["course_code"], ["courses.code"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    with op.batch_alter_table("literature_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_literature_items_course_code"), ["course_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_literature_items_status"), ["status"], unique=False)


def _add_study_hierarchy_columns() -> None:
    """Add `<term>/<subject>` study-folder columns to `courses` and category columns to `lectures`."""
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("term", sa.String(length=40), server_default="", nullable=False))
        batch_op.add_column(sa.Column("subject", sa.String(length=255), server_default="", nullable=False))
        batch_op.add_column(sa.Column("study_dir", sa.String(length=1024), server_default="", nullable=False))

    with op.batch_alter_table("lectures", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=60), server_default="", nullable=False))
        batch_op.add_column(
            sa.Column("relative_path", sa.String(length=1024), server_default="", nullable=False)
        )


def upgrade() -> None:
    """Add literature tables and study-hierarchy columns (split into helpers; schema unchanged)."""
    _create_literature_jobs()
    _create_literature_items()
    _add_study_hierarchy_columns()


def downgrade() -> None:
    """Revert this revision."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("lectures", schema=None) as batch_op:
        batch_op.drop_column("relative_path")
        batch_op.drop_column("category")

    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_column("study_dir")
        batch_op.drop_column("subject")
        batch_op.drop_column("term")

    with op.batch_alter_table("literature_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_literature_items_status"))
        batch_op.drop_index(batch_op.f("ix_literature_items_course_code"))

    op.drop_table("literature_items")
    op.drop_table("literature_jobs")
    # ### end Alembic commands ###
