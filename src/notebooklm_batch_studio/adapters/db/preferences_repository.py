"""Database access for web preferences (設計與自訂, layout, study memories), table `ui_preferences`."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import UiPreferenceRecord, utc_now

logger = logging.getLogger(__name__)


class PreferencesRepository:
    """Read and write the preference key-value pairs for one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session.

        Args:
            session: SQLAlchemy session (request-scoped in the web app).
        """
        self.session = session

    def all(self) -> dict[str, str]:
        """Return every stored preference.

        Returns:
            Mapping of key to value.
        """
        rows = self.session.scalars(select(UiPreferenceRecord)).all()
        return {row.key: row.value for row in rows}

    def apply(self, changes: dict[str, str | None]) -> None:
        """Save and delete preferences in one transaction (None deletes the key).

        Args:
            changes: Mapping of key to new value, or None to delete it.
        """
        for key, value in changes.items():
            row = self.session.get(UiPreferenceRecord, key)
            if value is None:
                if row is not None:
                    self.session.delete(row)
            elif row is None:
                self.session.add(UiPreferenceRecord(key=key, value=value, updated_at=utc_now()))
            else:
                row.value, row.updated_at = value, utc_now()
        self.session.commit()

    def delete_except(self, keep: list[str]) -> int:
        """Delete every preference except the listed keys.

        Args:
            keep: Keys to keep.

        Returns:
            Number of deleted preferences.
        """
        result = self.session.execute(delete(UiPreferenceRecord).where(UiPreferenceRecord.key.not_in(keep)))
        self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
