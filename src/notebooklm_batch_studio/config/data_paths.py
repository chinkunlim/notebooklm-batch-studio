"""Maintenance folders inside `DATA_DIR` (diagnostics, recoverable deletions, DB backups) for AppConfig."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MaintenancePathsMixin:
    """Path properties for maintenance folders; `AppConfig` supplies `data_dir`."""

    data_dir: Path

    @property
    def diagnostics_reports_dir(self) -> Path:
        """Directory inside `DATA_DIR` for diagnostic JSON reports such as consolidation plans.

        Returns:
            `<data_dir>/diagnostics`.
        """
        return self.data_dir / "diagnostics"

    @property
    def deleted_dir(self) -> Path:
        """Recoverable trash folder for deleted course legacy artifacts and pruned backups.

        Returns:
            `<data_dir>/deleted`.
        """
        return self.data_dir / "deleted"

    @property
    def backups_dir(self) -> Path:
        """Database backups written by `scripts/update.sh` before migrating (Refs: SPEC-017).

        Returns:
            `<data_dir>/backups`.
        """
        return self.data_dir / "backups"

    @property
    def note_schedule_path(self) -> Path:
        """Background Gemini note schedule written by `NoteScheduler` (Refs: SPEC-020).

        Returns:
            `<data_dir>/state/note_schedule.json`.
        """
        return self.data_dir / "state" / "note_schedule.json"

    @property
    def notebooklm_chrome_profile_dir(self) -> Path:
        """Own Chrome profile used to sign in to Gemini Notebook in real Chrome (Refs: SPEC-022).

        Returns:
            `<data_dir>/state/notebooklm_chrome_profile`.
        """
        return self.data_dir / "state" / "notebooklm_chrome_profile"

    @property
    def study_alerts_path(self) -> Path:
        """Keys of study/ alerts already sent as macOS notifications (Refs: SPEC-029).

        Returns:
            `<data_dir>/state/notified.json`.
        """
        return self.data_dir / "state" / "notified.json"
