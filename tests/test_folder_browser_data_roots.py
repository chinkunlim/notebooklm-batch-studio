"""ISSUE-078: the folder browser opens the study/scratch shortcuts even when DATA_DIR is outside home."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.services.folder_browser import browse_folders

logger = logging.getLogger(__name__)


class DataRootBrowseTest(unittest.TestCase):
    """Configured data folders are browsable; everything else outside home stays blocked."""

    def setUp(self) -> None:
        """Create a fake home and a DATA_DIR outside it (like an external drive)."""
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.home = base / "home"
        self.home.mkdir()
        self.cfg = AppConfig(data_dir=base / "external" / "data", database_url="sqlite://")
        self.cfg.ensure_data_dirs()
        (self.cfg.study_root_dir / "115-1" / "CP__1-x").mkdir(parents=True)
        self.outside = base / "elsewhere"
        self.outside.mkdir()

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def test_study_shortcut_and_its_subfolders_open(self) -> None:
        """study/ and folders beneath it can be browsed; going up stops at study/."""
        top = browse_folders(str(self.cfg.study_root_dir), self.cfg, home=self.home)
        self.assertEqual([f["name"] for f in top["folders"]], ["115-1"])
        self.assertIsNone(top["parent"])
        term = browse_folders(str(self.cfg.study_root_dir / "115-1"), self.cfg, home=self.home)
        self.assertEqual(term["parent"], str(self.cfg.study_root_dir.resolve()))

    def test_scratch_shortcut_opens(self) -> None:
        """scratch/ can be browsed too."""
        self.assertEqual(browse_folders(str(self.cfg.scratch_dir), self.cfg, home=self.home)["parent"], None)

    def test_other_folders_outside_home_stay_blocked(self) -> None:
        """Only home and the configured data folders are allowed."""
        for path in (self.outside, self.cfg.data_dir, self.cfg.data_dir / "db"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                browse_folders(str(path), self.cfg, home=self.home)


if __name__ == "__main__":
    unittest.main()
