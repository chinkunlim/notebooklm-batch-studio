"""TASK-036 #6: closing the ask drawer hands keyboard focus back; Escape closes it (accessibility)."""

from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"


class QaDrawerFocusTest(unittest.TestCase):
    """Focus never stays inside the hidden drawer."""

    def setUp(self) -> None:
        """Read the drawer script."""
        self.js = (STATIC / "studio-qa-drawer.js").read_text(encoding="utf-8")

    def test_closing_returns_focus_to_toggle_button(self) -> None:
        """toggleQaDrawer moves focus to #qaDrawerToggleBtn when the drawer closes with focus inside."""
        body = self.js[self.js.index("function toggleQaDrawer") :]
        body = body[: body.index("\n}\n")]
        self.assertIn("qaDrawerToggleBtn", body)
        self.assertRegex(body, r"drawer\.contains\(document\.activeElement\)")

    def test_escape_closes_open_drawer(self) -> None:
        """A keydown listener closes the open drawer on Escape."""
        pattern = r"e\.key === 'Escape'[^\n]*qaDrawer|qaDrawer[^\n]*e\.key === 'Escape'"
        self.assertTrue(re.search(pattern, self.js))


if __name__ == "__main__":
    unittest.main()
