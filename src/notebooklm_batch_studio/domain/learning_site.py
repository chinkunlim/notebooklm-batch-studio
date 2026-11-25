"""Learning-site Studio rows and the client protocol the site runner needs (SPEC-021).

A learning site is made by sending a "make me a site" chat prompt; Gemini Notebook then adds a
Studio item of type code 10 whose raw row carries the HTML file name and a download URL.
Refs: ISSUE-070 (the library's downloader refuses HTML, so the adapter downloads it itself).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SITE_TYPE_CODE = 10
SITE_MIME = "text/html"
STATUS_GENERATING = 2
STATUS_DONE = 3

# Raw Studio row positions observed on 2026-11-25 (fixture: tests/fixtures/notebooklm/site_row.json)
_ID, _TITLE, _TYPE, _STATUS, _CREATED, _FILE = 0, 1, 2, 4, 15, 24


@dataclass(frozen=True)
class SiteRow:
    """One learning-site item in a notebook's Studio.

    Attributes:
        id: Studio artifact id.
        title: Title shown in Studio.
        status: Raw status code (2 generating, 3 done, anything else failed).
        created: Creation time in epoch seconds.
        filename: HTML file name chosen by Gemini Notebook.
        download_url: Cookie-authenticated download URL (empty while generating).
    """

    id: str
    title: str
    status: int
    created: float
    filename: str
    download_url: str


def _created_seconds(value: Any) -> float:
    """Convert a raw `[seconds, nanos]` timestamp to epoch seconds.

    Args:
        value: Raw timestamp cell.

    Returns:
        Epoch seconds, or 0.0 when the cell is missing or malformed.
    """
    if isinstance(value, list) and value and isinstance(value[0], int | float):
        nanos = value[1] if len(value) > 1 and isinstance(value[1], int | float) else 0
        return float(value[0]) + float(nanos) / 1e9
    return 0.0


def _cell(row: list[Any], index: int) -> Any:
    """Read one cell of a raw row, tolerating short rows.

    Args:
        row: Raw Studio row.
        index: Cell position.

    Returns:
        The cell value, or None when the row is shorter.
    """
    return row[index] if len(row) > index else None


def parse_site_row(row: list[Any]) -> SiteRow | None:
    """Parse a raw Studio row into a SiteRow when it is a learning site.

    Args:
        row: Raw row from the notebook's Studio listing.

    Returns:
        SiteRow, or None when the row is not a type-10 HTML item.
    """
    if not isinstance(row, list) or _cell(row, _TYPE) != SITE_TYPE_CODE:
        return None
    file_info = _cell(row, _FILE)
    file_info = file_info if isinstance(file_info, list) else []
    mime = file_info[1] if len(file_info) > 1 else None
    status = _cell(row, _STATUS)
    # While generating, the file cell is still empty; only a present non-HTML MIME rules the row out.
    if mime not in (SITE_MIME, None) or not isinstance(status, int):
        return None
    return SiteRow(
        id=str(_cell(row, _ID) or ""),
        title=str(_cell(row, _TITLE) or ""),
        status=status,
        created=_created_seconds(_cell(row, _CREATED)),
        filename=str(file_info[0]) if file_info and file_info[0] else "",
        download_url=str(file_info[3]) if len(file_info) > 3 and file_info[3] else "",
    )


class LearningSiteClientProtocol(Protocol):
    """What the learning-site runner needs from the Gemini Notebook adapter."""

    async def list_site_rows(self, notebook_id: str) -> list[SiteRow]:
        """List the learning sites currently in a notebook's Studio.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Parsed site rows (any status).
        """
        ...

    async def request_site(self, notebook_id: str, prompt: str, source_ids: list[str]) -> str:
        """Send the site prompt through chat with only the given sources ticked.

        Args:
            notebook_id: Notebook identifier.
            prompt: Prompt starting with `make me a site`.
            source_ids: Sources the site is built from.

        Returns:
            Gemini Notebook's chat answer text.
        """
        ...

    async def download_site(self, row: SiteRow, output_path: str) -> None:
        """Download a finished site's HTML.

        Args:
            row: Finished site row.
            output_path: Local destination file.
        """
        ...

    def site_lock(self, notebook_id: str) -> asyncio.Lock:
        """Return the lock that serialises site requests for one notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            The same Lock object for the same notebook.
        """
        ...
