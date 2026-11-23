"""Offline tests for literature report rendering, preprint labeling, and note formatting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from notebooklm_batch_studio.adapters.literature.report_md import render_report_md  # noqa: E402
from notebooklm_batch_studio.domain.literature.literature import Reference, ReferenceKind  # noqa: E402
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem  # noqa: E402

WEBB_REF = Reference("Webb_2012", "Webb", doi="10.1037/a0027600", title="Dealing with feeling")
WEBB = TrackedItem(
    "Webb_2012",
    "Webb 2012",
    WEBB_REF,
    "Webb, T. L. (2012). *Dealing with feeling*.",
    ItemStatus.DOWNLOADED,
    file="Webb_2012.pdf",
    source="https://research.ebsco.com/x",
)
BECK_REF = Reference("Beck_1976", "Beck", kind=ReferenceKind.BOOK, title="Cognitive therapy")


class ReportRenderTest(unittest.TestCase):
    """Report Markdown rendering, preprint markers, and note formatting."""

    def test_preprint_server_download_is_marked_as_copy(self) -> None:
        """A PDF from arXiv / OSF is marked as a preprint/author copy in report.md."""
        item = TrackedItem(
            "K",
            "k",
            Reference("K", "k"),
            "k",
            ItemStatus.DOWNLOADED_COPY,
            file="K.pdf",
            source="https://arxiv.org/pdf/2506.08872",
            note="preprint",
        )
        self.assertIn("預印本", render_report_md([item], "out", "now"))

    def test_notes_use_chinese_separators(self) -> None:
        """Joined notes are separated with '；'."""
        item = TrackedItem(
            "B",
            "b",
            BECK_REF,
            "b",
            ItemStatus.BORROW,
            note="book: borrow from the library; latest edition: 2000",
        )
        text = render_report_md([item], "out", "now")
        self.assertIn("書籍：請向圖書館借閱；最新版本：2000", text)

    def test_downloaded_item_renders_in_report(self) -> None:
        """Downloaded items include their APA citation and file name in report.md."""
        text = render_report_md([WEBB], "out", "now")
        self.assertIn("Webb_2012.pdf", text)
        self.assertIn("Dealing with feeling", text)


if __name__ == "__main__":
    unittest.main()
