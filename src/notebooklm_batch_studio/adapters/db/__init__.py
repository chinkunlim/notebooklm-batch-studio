"""Database adapters package: repositories, session management, and ORM base."""

from __future__ import annotations

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import (
    CourseRepository,
    QueueRepository,
)
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope

__all__ = [
    "Base",
    "CourseRepository",
    "QueueRepository",
    "create_db_engine",
    "session_scope",
]
