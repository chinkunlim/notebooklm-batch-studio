"""TASK-036 #10: the 未歸檔檔案 card can file into 03 Notes, which requires a subfolder (ISSUE-077)."""

from __future__ import annotations

import logging
import unittest
from pathlib import Path

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"


class UnfiledSubfolderTest(unittest.TestCase):
    """Each unfiled row has a subfolder picker and sends `subfolder` to /api/study/file."""

    def setUp(self) -> None:
        """Read the library script."""
        self.js = (STATIC / "studio-library.js").read_text(encoding="utf-8")

    def _function(self, name: str) -> str:
        """Return the source of one top-level function.

        Args:
            name: Function name.

        Returns:
            Source from its declaration to the closing brace.
        """
        body = self.js[self.js.index(f"function {name}(") :]
        return body[: body.index("\n}\n")]

    def test_rows_have_a_subfolder_picker(self) -> None:
        """The card renders a subfolder <select> wired to the shared picker (path rule: chosen, not typed)."""
        card = self._function("loadUnfiledCard")
        self.assertIn('id="unfSub${i}"', card)
        self.assertIn("onSubfolderPick(this)", card)

    def test_filing_sends_subfolder_and_requires_it_for_notes(self) -> None:
        """fileLibraryItem posts `subfolder` and stops early for 03 Notes without one."""
        body = self._function("fileLibraryItem")
        self.assertIn("subfolder", body)
        self.assertIn("'notes'", body)


if __name__ == "__main__":
    unittest.main()
