"""SPEC-023: the old migrate-study-layout tool is retired in favour of `consolidate`."""

from __future__ import annotations

import importlib.util
import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server

logger = logging.getLogger(__name__)


class MigrateStudyLayoutRetiredTest(unittest.TestCase):
    """HTTP answers 410 without touching anything; MCP no longer offers the tool; the code is gone."""

    def setUp(self) -> None:
        """Create an isolated configuration with a legacy flat course folder."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name) / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.legacy = data_dir / "input" / "courses" / "115-1 心理學研究法"
        self.legacy.mkdir(parents=True)
        (self.legacy / "Ch01.pdf").write_bytes(b"%PDF-1.4\n")

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def test_http_route_returns_410_and_moves_nothing(self) -> None:
        """Even `dry_run: false` (the old default) changes nothing and points to consolidate."""
        res = TestClient(create_app(config=self.cfg)).post(
            "/api/courses/migrate-study-layout", json={"dry_run": False}
        )
        self.assertEqual(res.status_code, 410)
        self.assertIn("consolidate", res.json()["detail"])
        self.assertTrue((self.legacy / "Ch01.pdf").is_file())
        self.assertFalse(any(self.cfg.study_root_dir.rglob("*.pdf")))

    def test_openapi_marks_route_deprecated(self) -> None:
        """Open WebUI sees the route as deprecated."""
        spec = TestClient(create_app(config=self.cfg)).get("/openapi.json").json()
        self.assertTrue(spec["paths"]["/api/courses/migrate-study-layout"]["post"]["deprecated"])

    def test_mcp_tool_is_gone(self) -> None:
        """AI tools can no longer call migrate_study_layout."""
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertNotIn("migrate_study_layout", tools)

    def test_old_service_code_is_removed(self) -> None:
        """The migration service and its repository no longer exist."""
        for name in (
            "notebooklm_batch_studio.services.study_migration",
            "notebooklm_batch_studio.adapters.db.study_migration_repo",
        ):
            with self.subTest(module=name):
                self.assertIsNone(importlib.util.find_spec(name))


if __name__ == "__main__":
    unittest.main()
