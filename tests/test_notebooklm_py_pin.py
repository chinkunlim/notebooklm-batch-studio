"""SPEC-025 R2: notebooklm-py stays pinned; learning sites depend on its internal Studio API."""

from __future__ import annotations

import logging
import re
import tomllib
import unittest
from importlib.metadata import version
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PINNED = "0.8.6"
HOW_TO_UPGRADE = (
    "升級 notebooklm-py 前先照 docs/standards/PROJECT_RULES.md「升級 notebooklm-py」逐項檢查，"
    "再改這裡的 PINNED"
)


class NotebooklmPyPinTest(unittest.TestCase):
    """An upgrade must be deliberate: pyproject and the installed package name the same version."""

    def test_pyproject_pins_exact_version(self) -> None:
        """pyproject.toml uses `==`, so `uv lock --upgrade` cannot move it silently."""
        deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        spec = next(d for d in deps if d.startswith("notebooklm-py"))
        self.assertRegex(spec, rf"=={re.escape(PINNED)}$", HOW_TO_UPGRADE)

    def test_installed_version_matches_pin(self) -> None:
        """The environment runs the version the learning-site tests were written against."""
        self.assertEqual(version("notebooklm-py"), PINNED, HOW_TO_UPGRADE)

    def test_project_rules_describe_the_upgrade_check(self) -> None:
        """The upgrade checklist exists where the failure message points."""
        rules = (ROOT / "docs" / "standards" / "PROJECT_RULES.md").read_text(encoding="utf-8")
        self.assertIn("升級 notebooklm-py", rules)
        self.assertIn("test_learning_site", rules)


if __name__ == "__main__":
    unittest.main()
