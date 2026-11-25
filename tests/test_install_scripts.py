"""Tests for the one-click install and update scripts (core rule 14, env/install_and_update.md)."""

from __future__ import annotations

import logging
import os
import subprocess
import unittest
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "install.sh"
UPDATE = ROOT / "scripts" / "update.sh"


def _ordered(text: str, needles: list[str]) -> bool:
    """Return True when every needle appears in `text` in the given order.

    Args:
        text: Script source.
        needles: Substrings expected in order.

    Returns:
        Whether all needles occur in order.
    """
    pos = 0
    for needle in needles:
        found = text.find(needle, pos)
        if found < 0:
            return False
        pos = found + len(needle)
    return True


class InstallScriptsTests(unittest.TestCase):
    """The install/update scripts exist, parse, and run the required steps in order."""

    def test_scripts_exist_are_executable_and_parse(self) -> None:
        """Both scripts are executable and pass `bash -n` syntax checking."""
        for script in (INSTALL, UPDATE):
            self.assertTrue(script.is_file(), script)
            self.assertTrue(os.access(script, os.X_OK), f"{script} not executable")
            res = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_install_runs_required_steps_in_order(self) -> None:
        """Install checks tools, prepares env and DATA_DIR, installs locked deps, migrates, initializes."""
        text = INSTALL.read_text(encoding="utf-8")
        self.assertTrue(
            _ordered(
                text,
                [
                    "command -v uv",
                    "agentctl.py doctor --fix",
                    "agentctl.py setup --install",
                    "alembic upgrade head",
                    "notebooklm-batch-studio init-data",
                ],
            )
        )

    def test_update_backs_up_db_before_migrating_and_never_resets_env(self) -> None:
        """Update pulls fast-forward only, refuses while server runs, backs up DB before migration."""
        text = UPDATE.read_text(encoding="utf-8")
        self.assertTrue(
            _ordered(
                text,
                [
                    "pull --ff-only",
                    "agentctl.py setup --install",
                    "server_running",
                    ".backup(",
                    "alembic upgrade head",
                    "notebooklm-batch-studio init-data",
                ],
            )
        )
        self.assertNotIn(".env.example", text)

    def test_readme_lists_fresh_install_and_update_commands(self) -> None:
        """README documents both one-command entry points."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("./scripts/install.sh", readme)
        self.assertIn("./scripts/update.sh", readme)


if __name__ == "__main__":
    unittest.main()
