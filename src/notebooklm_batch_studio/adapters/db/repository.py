"""Greeting repository: stores and reads greetings, returning domain objects."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import GreetingRecord
from notebooklm_batch_studio.domain.models import GreetingResult


class GreetingRepository:
    """Database access for greetings (the only place that touches `GreetingRecord`)."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an open session.

        Args:
            session: Session from `session_scope()`.
        """
        self.session = session

    def add(self, user_name: str, result: GreetingResult) -> int:
        """Store one greeting.

        Args:
            user_name: Name that was greeted.
            result: Greeting produced by the service layer.

        Returns:
            The new row ID.
        """
        record = GreetingRecord(user_name=user_name, message=result.message)
        self.session.add(record)
        self.session.flush()
        return record.id

    def recent(self, limit: int = 20, environment: str = "") -> list[GreetingResult]:
        """Return the newest greetings first.

        Args:
            limit: Maximum number of rows.
            environment: Environment name copied into the returned domain objects.

        Returns:
            Greetings as domain objects.
        """
        stmt = select(GreetingRecord).order_by(GreetingRecord.id.desc()).limit(limit)
        rows = self.session.scalars(stmt)
        return [GreetingResult(message=r.message, environment=environment) for r in rows]
