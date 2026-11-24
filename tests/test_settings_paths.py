"""Tests for centralized AppConfig paths, no implicit load_config(), and init-data (SPEC-014 §5.3)."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole
from notebooklm_batch_studio.entrypoints.cli import main


class SettingsPathsTests(unittest.TestCase):
    """Verify AppConfig centralized subpaths, zero hardcoded paths, and init-data."""

    def test_new_paths_within_data_dir_and_study_layout(self) -> None:
        """All new DATA_DIR subpaths resolve inside data_dir; study_layout honors overrides."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(data_dir=Path(tmp))
            for attr in (
                "gemini_profile_dir",
                "diagnostics_dir",
                "deleted_dir",
                "prompt_override_dir",
                "notes_state_dir",
            ):
                resolved = getattr(cfg, attr)
                self.assertTrue(resolved.is_relative_to(cfg.data_dir), attr)

            self.assertEqual(cfg.study_layout, DEFAULT_LAYOUT)
            custom = AppConfig(data_dir=Path(tmp), study_categories="A, B, C, D, E")
            self.assertEqual(custom.study_layout.names[CategoryRole.HANDOUTS], "B")

    def test_scratch_kind_dir_validates_kind(self) -> None:
        """scratch_kind_dir permits only the 5 fixed kinds and rejects traversal/unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(data_dir=Path(tmp))
            for kind in ("literature", "notes", "outputs", "uploads", "unarchived"):
                path = cfg.scratch_kind_dir(kind)
                self.assertEqual(path, cfg.scratch_dir / kind)
                self.assertTrue(path.is_relative_to(cfg.scratch_dir))
            with self.assertRaises(ValueError):
                cfg.scratch_kind_dir("../x")
            with self.assertRaises(ValueError):
                cfg.scratch_kind_dir("other")

    def test_no_hardcoded_data_dir_subpaths_outside_config(self) -> None:
        """No module outside config/ builds paths directly with data_dir/state_dir/scratch_dir/... / '...'."""
        hits: list[str] = []
        pattern = re.compile(r'(data_dir|state_dir|scratch_dir|output_dir|input_dir)\s*/\s*"')
        for py_file in Path("src/notebooklm_batch_studio").rglob("*.py"):
            if py_file.parent.name == "config":
                continue
            text = py_file.read_text(encoding="utf-8")
            for idx, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{py_file}:{idx}: {line.strip()}")
        self.assertEqual(hits, [])

    def test_no_implicit_load_config_outside_entrypoints_and_config(self) -> None:
        """load_config() is called only in entrypoints/ and defined in config/."""
        hits: list[str] = []
        for py_file in Path("src/notebooklm_batch_studio").rglob("*.py"):
            if "entrypoints" in py_file.parts or "config" in py_file.parts:
                continue
            text = py_file.read_text(encoding="utf-8")
            if "load_config(" in text:
                hits.append(str(py_file))
        self.assertEqual(hits, [])

    def test_init_data_creates_study_and_scratch_idempotently(self) -> None:
        """CLI init-data creates study/ and all 5 scratch/<kind>/ folders cleanly and idempotently."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "isolated_data"
            with (
                mock.patch("notebooklm_batch_studio.config.settings.load_dotenv_file"),
                mock.patch.dict(os.environ, {"DATA_DIR": str(data_dir), "LOG_TO_FILE": "false"}),
            ):
                code1 = main(["init-data"])
                code2 = main(["init-data"])
            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            self.assertTrue((data_dir / "study").is_dir())
            for kind in ("literature", "notes", "outputs", "uploads", "unarchived"):
                self.assertTrue((data_dir / "scratch" / kind).is_dir(), kind)


if __name__ == "__main__":
    unittest.main()
