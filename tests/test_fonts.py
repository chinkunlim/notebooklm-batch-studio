"""Fonts: the user downloads free Google Fonts into DATA_DIR/fonts and uses them offline (ADR-009)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.fonts.google_fonts import GoogleFontsClient
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import FontDownloadError
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.font_service import FontService

CSS = """/* [0] */
@font-face {
  font-family: 'LXGW WenKai TC';
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/lxgw/v1/a.woff2) format('woff2');
  unicode-range: U+4e00-4eff;
}
@font-face {
  font-family: 'LXGW WenKai TC';
  font-weight: 700;
  src: url(https://fonts.gstatic.com/s/lxgw/v1/b.woff2) format('woff2');
}
"""


class FakeGet:
    """Stands in for the internet: returns the CSS and two small font files, and records the requests."""

    def __init__(self, fail_weights: bool = False, font_size: int = 10) -> None:
        """Set up the fake.

        Args:
            fail_weights: Answer 400 when specific weights are asked for (like a family without them).
            font_size: Bytes in each font file.
        """
        self.fail_weights = fail_weights
        self.font_size = font_size
        self.urls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> bytes:
        """Return the fake response for a URL.

        Args:
            url: Requested URL.
            headers: Request headers (the User-Agent must ask for woff2).
            timeout: Timeout in seconds.

        Returns:
            Response body.

        Raises:
            FontDownloadError: For the weight request when fail_weights is set.
        """
        self.urls.append(url)
        if "fonts.googleapis.com" in url:
            if self.fail_weights and "wght" in url:
                raise FontDownloadError("HTTP 400")
            assert "Mozilla" in headers["User-Agent"]
            return CSS.encode()
        return b"x" * self.font_size


class FontServiceTest(unittest.TestCase):
    """Download, list, serve and delete fonts."""

    def setUp(self) -> None:
        """Create a temporary DATA_DIR."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.fonts_dir = Path(self.tmpdir.name) / "fonts"

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def service(self, get: FakeGet, max_bytes: int = 1_000_000) -> FontService:
        """Build a font service with a fake download.

        Args:
            get: Fake HTTP getter.
            max_bytes: Size cap per family.

        Returns:
            FontService.
        """
        return FontService(self.fonts_dir, GoogleFontsClient(get=get, max_bytes=max_bytes))

    def test_install_rewrites_css_to_local_files(self) -> None:
        """Every font file is saved next to font.css and the CSS points at the local copies."""
        get = FakeGet()
        meta = self.service(get).install("LXGW WenKai TC")
        self.assertEqual(
            (meta["slug"], meta["family"], meta["files"]), ("lxgw-wenkai-tc", "LXGW WenKai TC", 2)
        )
        css = (self.fonts_dir / "lxgw-wenkai-tc" / "font.css").read_text(encoding="utf-8")
        self.assertNotIn("gstatic", css)
        self.assertIn('url("000.woff2")', css)
        self.assertTrue((self.fonts_dir / "lxgw-wenkai-tc" / "001.woff2").exists())
        self.assertIn("family=LXGW+WenKai+TC", get.urls[0])

    def test_family_without_weights_falls_back(self) -> None:
        """A family that does not have 500/700 is downloaded with its default weight."""
        get = FakeGet(fail_weights=True)
        self.service(get).install("Some Font")
        self.assertNotIn("wght", get.urls[1])

    def test_size_cap_and_bad_names(self) -> None:
        """Too large a family is refused and leaves nothing behind; odd names are refused."""
        with self.assertRaises(FontDownloadError):
            self.service(FakeGet(font_size=600), max_bytes=1000).install("Big Font")
        self.assertEqual(self.service(FakeGet()).list_fonts(), [])
        for bad in ("../etc", "a" * 61, "", "字型"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.service(FakeGet()).install(bad)

    def test_list_file_path_and_delete(self) -> None:
        """Installed fonts are listed; only files inside a font's folder are served; delete removes it."""
        svc = self.service(FakeGet())
        svc.install("LXGW WenKai TC")
        self.assertEqual([f["family"] for f in svc.list_fonts()], ["LXGW WenKai TC"])
        self.assertTrue(svc.file_path("lxgw-wenkai-tc", "font.css").exists())
        for slug, name in (
            ("lxgw-wenkai-tc", "../meta.json"),
            ("..", "font.css"),
            ("lxgw-wenkai-tc", "nope.woff2"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                svc.file_path(slug, name)
        self.assertTrue(svc.delete("lxgw-wenkai-tc"))
        self.assertEqual(svc.list_fonts(), [])

    def test_http_and_mcp(self) -> None:
        """HTTP lists, installs, serves and deletes; MCP changes need confirm=True."""
        config = AppConfig(
            data_dir=Path(self.tmpdir.name) / "data",
            notebooklm_home=Path(self.tmpdir.name) / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        svc = self.service(FakeGet())
        app = create_app(config=config, service=mock.MagicMock(), study_service=mock.MagicMock())
        app.state.fonts = svc
        http = TestClient(app)
        self.assertEqual(http.post("/api/fonts", json={"family": "LXGW WenKai TC"}).status_code, 200)
        self.assertEqual(http.post("/api/fonts", json={"family": "../x"}).status_code, 400)
        self.assertEqual(http.get("/api/fonts").json()["fonts"][0]["slug"], "lxgw-wenkai-tc")
        res = http.get("/api/fonts/lxgw-wenkai-tc/font.css")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/css", res.headers["content-type"])
        self.assertEqual(http.get("/api/fonts/lxgw-wenkai-tc/meta.json").status_code, 404)
        mcp = build_mcp_server(
            service=mock.MagicMock(), study_service=mock.MagicMock(), config=config, fonts=svc
        )
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertIn("confirm", json.loads(tools["delete_font"].fn("lxgw-wenkai-tc")))
        self.assertEqual(len(json.loads(tools["list_fonts"].fn())["fonts"]), 1)
        self.assertEqual(http.delete("/api/fonts/lxgw-wenkai-tc").status_code, 200)
        self.assertIn("confirm", json.loads(tools["install_google_font"].fn("Noto Sans TC")))


if __name__ == "__main__":
    unittest.main()
