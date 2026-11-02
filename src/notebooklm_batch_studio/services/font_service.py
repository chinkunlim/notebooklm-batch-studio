"""Fonts the user downloaded from Google Fonts, kept in DATA_DIR/fonts/<slug>/ (ADR-009).

Each font folder holds `font.css`, its woff2 files and `meta.json`. The web page loads
`/api/fonts/<slug>/font.css`, so a downloaded font works offline.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.domain.exceptions import FontDownloadError

logger = logging.getLogger(__name__)

FAMILY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{0,59}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9-]{1,60}$")
FILE_PATTERN = re.compile(r"^(font\.css|\d{3}\.woff2)$")


class FontDownloader(Protocol):
    """Downloads one font family into a folder."""

    def download(self, family: str, dest: Path) -> dict[str, Any]:
        """Download a family into `dest`.

        Args:
            family: Font family name.
            dest: Folder to write into.

        Returns:
            {"files": count, "bytes": total size}.
        """
        ...


class FontService:
    """List, install, serve and delete downloaded fonts."""

    def __init__(self, fonts_dir: Path, downloader: FontDownloader) -> None:
        """Create the service.

        Args:
            fonts_dir: DATA_DIR/fonts.
            downloader: Google Fonts downloader.
        """
        self.fonts_dir = fonts_dir
        self.downloader = downloader

    def list_fonts(self) -> list[dict[str, Any]]:
        """Return every downloaded font, sorted by family name.

        Returns:
            Font descriptions (family, slug, css URL, files, bytes, downloaded_at).
        """
        if not self.fonts_dir.is_dir():
            return []
        fonts = []
        for meta in self.fonts_dir.glob("*/meta.json"):
            try:
                fonts.append(json.loads(meta.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("Skipping unreadable font metadata %s", meta)
        return sorted(fonts, key=lambda f: str(f.get("family", "")).lower())

    def install(self, family: str) -> dict[str, Any]:
        """Download a Google Fonts family (or return it when it is already downloaded).

        Args:
            family: Family name exactly as on fonts.google.com, e.g. "LXGW WenKai TC".

        Returns:
            The font's description.

        Raises:
            ValueError: The name is not a plain font family name.
            FontDownloadError: The download failed (nothing is left behind).
        """
        family = " ".join(family.split())
        if not FAMILY_PATTERN.match(family):
            raise ValueError(
                "font family name: 1-60 English letters, digits and spaces (as on fonts.google.com)"
            )
        slug = family.lower().replace(" ", "-")
        target = self.fonts_dir / slug
        if (target / "meta.json").exists():
            return dict(json.loads((target / "meta.json").read_text(encoding="utf-8")))
        tmp = self.fonts_dir / f".{slug}.part"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            stats = self.downloader.download(family, tmp)
        except FontDownloadError:
            shutil.rmtree(tmp, ignore_errors=True)
            logger.warning("Font download failed: %s", family)
            raise
        meta = {
            "family": family,
            "slug": slug,
            "css": f"/api/fonts/{slug}/font.css",
            "downloaded_at": datetime.now(UTC).isoformat(),
            **stats,
        }
        (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(target)
        logger.info("Installed font %s (%s)", family, slug)
        return meta

    def file_path(self, slug: str, name: str) -> Path:
        """Path of one servable file of a downloaded font (font.css or a woff2 file).

        Args:
            slug: Font folder name.
            name: File name.

        Returns:
            Existing file path inside the font's folder.

        Raises:
            ValueError: Not a font folder, not a servable file name, or the file does not exist.
        """
        if not SLUG_PATTERN.match(slug) or not FILE_PATTERN.match(name):
            raise ValueError("not a font file")
        path = (self.fonts_dir / slug / name).resolve()
        if self.fonts_dir.resolve() not in path.parents or not path.is_file():
            raise ValueError("not a font file")
        return path

    def delete(self, slug: str) -> bool:
        """Delete a downloaded font.

        Args:
            slug: Font folder name.

        Returns:
            True when it existed and was removed.

        Raises:
            ValueError: Not a valid font folder name.
        """
        if not SLUG_PATTERN.match(slug):
            raise ValueError("not a font folder")
        target = self.fonts_dir / slug
        if not target.is_dir():
            return False
        shutil.rmtree(target)
        logger.info("Deleted font %s", slug)
        return True
