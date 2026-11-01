"""NotebookLM was renamed Gemini Notebook (2026-07-16): no old name in what users see (ADR-006)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from notebooklm_batch_studio.domain.naming import naming_guide
from notebooklm_batch_studio.domain.usage_guide import USAGE_GUIDE

PKG = Path(__file__).resolve().parents[1] / "src/notebooklm_batch_studio"
OLD_NAME = re.compile(r"\bNotebookLM\b")


class RenameTest(unittest.TestCase):
    """User-facing text uses the new name; the usage guide explains the rename once."""

    def test_web_page_has_no_old_name(self) -> None:
        """The web page, its scripts and styles never show 'NotebookLM'."""
        for path in (PKG / "entrypoints/static").glob("*.*"):
            if path.suffix not in {".html", ".js", ".css", ".webmanifest"}:
                continue
            with self.subTest(file=path.name):
                self.assertIsNone(OLD_NAME.search(path.read_text(encoding="utf-8")))

    def test_guides_use_new_name(self) -> None:
        """Guides say Gemini Notebook; only the rename note mentions the old name."""
        text = str(naming_guide()) + str(USAGE_GUIDE["sections"])
        self.assertIsNone(OLD_NAME.search(text))
        self.assertIn("NotebookLM", USAGE_GUIDE["note"])
        self.assertIn("Gemini Notebook", text)

    def test_notebook_links_use_new_domain(self) -> None:
        """Links to a notebook point at notebook.google.com (the old domain only redirects)."""
        for path in PKG.rglob("*.py"):
            with self.subTest(file=path.name):
                self.assertNotIn("notebooklm.google.com", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
