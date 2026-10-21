"""ORM models (database tables). Only the adapters layer imports these."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from notebooklm_batch_studio.adapters.db.base import Base


def utc_now() -> datetime:
    """Return the current time in UTC (default for timestamp columns).

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


class GreetingRecord(Base):
    """One stored greeting (table `greetings`).

    Attributes:
        id: Primary key.
        user_name: Name that was greeted.
        message: Greeting text.
        created_at: When the greeting was stored (UTC).
    """

    __tablename__ = "greetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
