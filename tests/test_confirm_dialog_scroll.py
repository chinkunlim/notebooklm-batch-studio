"""ISSUE-074: long confirm dialogs (e.g. a 17-chapter split preview) must keep their buttons on screen."""

from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CSS = STATIC / "studio.css"


def rule(css: str, selector: str) -> str:
    """Return the declarations of the first rule whose selector list starts with `selector`.

    Args:
        css: Stylesheet text.
        selector: Selector that opens the rule.

    Returns:
        Declarations between the braces.
    """
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, selector
    return match.group(1)


class ConfirmDialogScrollTest(unittest.TestCase):
    """The dialog fits the viewport and only its text scrolls."""

    def test_box_is_capped_and_text_scrolls(self) -> None:
        """Box height is limited to the viewport; the text area scrolls; buttons stay visible."""
        css = CSS.read_text(encoding="utf-8")
        box = rule(css, "#confirmBox, #pickBox")
        self.assertIn("max-height", box)
        self.assertIn("flex-direction: column", box)
        text = rule(css, "#confirmText, #pickText")
        self.assertIn("overflow-y: auto", text)
        self.assertIn("min-height: 0", text)
        actions = rule(css, "#confirmBox .actions, #pickBox .actions")
        self.assertIn("flex-shrink: 0", actions)


if __name__ == "__main__":
    unittest.main()
