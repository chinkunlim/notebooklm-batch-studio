"""ISSUE-076: the web UI never uses the browser's own prompt / confirm / alert dialogs.

The Claude desktop app's browser pane throws on `prompt()`, answers `confirm()` with "cancel" and
drops `alert()` silently, so buttons built on them did nothing there. In-page dialogs work everywhere.
"""

from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
NATIVE = re.compile(r"(?<![\w.$])(?:window\.)?(prompt|confirm|alert)\s*\(")


def _code_lines(text: str) -> list[tuple[int, str]]:
    """Return non-comment lines with their numbers.

    Args:
        text: JavaScript source.

    Returns:
        `(line number, line)` pairs, skipping `//` and JSDoc lines.
    """
    lines = []
    for no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith(("//", "*", "/*")):
            lines.append((no, line))
    return lines


class NoNativeDialogsTest(unittest.TestCase):
    """Every script uses askText / askConfirm / showToast instead."""

    def test_no_prompt_confirm_or_alert(self) -> None:
        """No call to prompt(), confirm(), alert() (or their window. forms) in any static script."""
        hits = [
            f"{js.name}:{no}: {line.strip()[:90]}"
            for js in sorted(STATIC.glob("*.js"))
            for no, line in _code_lines(js.read_text(encoding="utf-8"))
            if NATIVE.search(line)
        ]
        self.assertEqual(hits, [], "\n".join(hits))

    def test_ask_text_dialog_exists(self) -> None:
        """The in-page text dialog that replaces prompt() is defined."""
        self.assertIn("function askText(", (STATIC / "studio-pickers.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
