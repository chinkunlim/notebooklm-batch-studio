"""Web preferences recorded on this computer (ADR-009): palette, layout, column widths, avatar, fonts,
and small study memories such as the audio position per lecture. The web page keeps a browser cache
for the first paint; this service (SQLite in DATA_DIR) is the source of truth."""

from __future__ import annotations

import logging
import re

from notebooklm_batch_studio.domain.repositories import PreferencesRepositoryProtocol

logger = logging.getLogger(__name__)

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
MAX_VALUE_CHARS = 512 * 1024
MAX_KEYS = 2000


class PreferencesService:
    """Validate and store preference key-value pairs."""

    def __init__(self, repo: PreferencesRepositoryProtocol) -> None:
        """Create the service.

        Args:
            repo: Preference storage.
        """
        self.repo = repo

    def get_all(self) -> dict[str, str]:
        """Return every stored preference.

        Returns:
            Mapping of key to value.
        """
        return self.repo.all()

    def update(self, changes: dict[str, str | None]) -> dict[str, str]:
        """Save some preferences and delete others (None deletes); nothing is saved if one is invalid.

        Args:
            changes: Mapping of key to new value, or None to delete it.

        Returns:
            Every stored preference after the change.

        Raises:
            ValueError: A key is not a short plain name, a value is too large, or too many keys.
        """
        for key, value in changes.items():
            if not KEY_PATTERN.match(key):
                raise ValueError(f"preference key must be 1-120 letters, digits or . _ : - : {key[:40]!r}")
            if value is not None and len(value) > MAX_VALUE_CHARS:
                raise ValueError(f"preference {key!r} is larger than {MAX_VALUE_CHARS} characters")
        current = self.repo.all()
        added = {k for k, v in changes.items() if v is not None and k not in current}
        if len(current) + len(added) > MAX_KEYS:
            raise ValueError(f"at most {MAX_KEYS} preferences can be stored")
        self.repo.apply(changes)
        logger.info("Saved %d preference change(s)", len(changes))
        return self.repo.all()

    def reset(self, keep: list[str]) -> dict[str, str]:
        """Delete every preference except the listed keys (the page's 「全部恢復預設」).

        Args:
            keep: Keys to keep, e.g. ["customPalettes", "course"].

        Returns:
            Every stored preference after the reset.
        """
        removed = self.repo.delete_except(keep)
        logger.info("Reset preferences: removed %d, kept %s", removed, keep)
        return self.repo.all()
