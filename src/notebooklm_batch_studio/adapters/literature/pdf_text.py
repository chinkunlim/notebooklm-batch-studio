"""PDF text adapter: extracts first-page text with pypdf for the wrong-paper check."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>\]\)]+)")
# pypdf warns about every font it cannot fully decode; that noise does not affect title checks
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PypdfTextReader:
    """Reads the text layer of the first pages of a PDF."""

    def __init__(self, pages: int = 2) -> None:
        """Create the reader.

        Args:
            pages: How many leading pages to read (cover pages often come first).
        """
        self._pages = pages

    def first_pages_text(self, data: bytes) -> str:
        """Extract text from the first pages.

        Args:
            data: PDF content.

        Returns:
            Extracted text; empty when the PDF has no text layer or cannot be parsed.
        """
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages[: self._pages])
        except (PyPdfError, ValueError, KeyError, TypeError) as exc:
            logger.warning("pdf text extraction failed: %s", exc)
            return ""


def extract_pdf_hint(path: Path) -> str:
    """Extract a DOI, PDF title metadata, or readable stem from a PDF file for source lookup.

    Args:
        path: Path to the local PDF file.

    Returns:
        DOI string if found, else PDF metadata title or cleaned filename stem.
    """
    try:
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
        match = _DOI_RE.search(text)
        if match:
            return match.group(1).rstrip(".,;:")
        title = str(getattr(reader.metadata, "title", "") or "").strip()
        if title and title.lower() not in ("untitled", "document") and not title.lower().endswith(".pdf"):
            return title
    except (PyPdfError, OSError, ValueError, KeyError, TypeError) as exc:
        logger.debug("Could not extract PDF hint from %s: %s", path.name, exc)
    return path.stem.replace("_", " ")
