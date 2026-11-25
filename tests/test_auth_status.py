"""Tests for three-profile sign-in status overview without secret leakage (SPEC-014 Task 14)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.session import create_db_engine
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.auth_status import sign_in_status


class AuthStatusOverviewTests(unittest.TestCase):
    """Verify NotebookLM, Gemini Web, and library sign-in status overview across ready/missing/expired."""

    def setUp(self) -> None:
        """Create isolated config paths and SQLite DB for auth status checks."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        nlm_home = root / "nlm_home"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            notebooklm_home=nlm_home,
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temp directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_missing_ready_and_expired_states_without_reading_secret_files(self) -> None:
        """States transition ready/missing/expired without reading NotebookLM or library cookie files."""
        gemini_auth = mock.MagicMock()
        gemini_auth.check_auth_status.return_value = {"logged_in": False}

        # 1. All missing initially
        rows_missing = sign_in_status(self.cfg, gemini_auth)
        self.assertEqual(len(rows_missing), 3)
        for r in rows_missing:
            self.assertLessEqual({"name", "location", "state", "how_to_sign_in"}, set(r.keys()))
            self.assertLessEqual(
                set(r.keys()), {"name", "location", "state", "how_to_sign_in", "login_route"}
            )
            self.assertEqual(r["state"], "missing")

        # 2. Populate NotebookLM & library files containing fake secret tokens + Gemini ready
        nlm_state = self.cfg.notebooklm_home / "profiles" / "default" / "storage_state.json"
        nlm_state.parent.mkdir(parents=True, exist_ok=True)
        nlm_state.write_text('{"cookies": [{"value": "SECRET_NLM_TOKEN"}]}', encoding="utf-8")

        self.cfg.literature_browser_profile_dir.mkdir(parents=True, exist_ok=True)
        lit_cookie = self.cfg.literature_browser_profile_dir / "Cookies"
        lit_cookie.write_text("SECRET_LIB_COOKIE", encoding="utf-8")

        gemini_auth.check_auth_status.return_value = {"logged_in": True}
        with mock.patch(
            "pathlib.Path.read_text", side_effect=AssertionError("Must not read credential files!")
        ):
            rows_ready = sign_in_status(self.cfg, gemini_auth)
        self.assertEqual([r["state"] for r in rows_ready], ["ready", "ready", "ready"])
        serialized = json.dumps(rows_ready, ensure_ascii=False)
        self.assertNotIn("SECRET_NLM_TOKEN", serialized)
        self.assertNotIn("SECRET_LIB_COOKIE", serialized)

        # 3. Expired Gemini session (storage_state.json exists, but logged_in=False)
        gemini_state = self.cfg.gemini_profile_dir / "storage_state.json"
        gemini_state.parent.mkdir(parents=True, exist_ok=True)
        gemini_state.write_text('{"cookies": []}', encoding="utf-8")
        gemini_auth.check_auth_status.return_value = {"logged_in": False}
        rows_expired = sign_in_status(self.cfg, gemini_auth)
        by_name = {r["name"]: r for r in rows_expired}
        self.assertEqual(by_name["Gemini 網頁"]["state"], "expired")

    def test_http_and_mcp_expose_sign_in_status_without_secrets(self) -> None:
        """HTTP GET /api/system/sign-ins and MCP get_sign_in_status return 3 sanitized rows."""
        nlm_state = self.cfg.notebooklm_home / "profiles" / "default" / "storage_state.json"
        nlm_state.parent.mkdir(parents=True, exist_ok=True)
        nlm_state.write_text('{"secret": "TOKEN_ABC"}', encoding="utf-8")

        app = create_app(config=self.cfg)
        app.state.gemini_auth = mock.MagicMock()
        app.state.gemini_auth.check_auth_status.return_value = {"logged_in": False}
        client = TestClient(app)

        resp = client.get("/api/system/sign-ins")
        self.assertEqual(resp.status_code, 200)
        sign_ins = resp.json()["sign_ins"]
        self.assertEqual(len(sign_ins), 3)
        self.assertEqual(sign_ins[0]["state"], "ready")
        self.assertNotIn("TOKEN_ABC", resp.text)

        mcp = build_mcp_server(config=self.cfg, gemini_auth=app.state.gemini_auth)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertIn("get_sign_in_status", tools)
        mcp_payload = json.loads(tools["get_sign_in_status"].fn())
        self.assertEqual(len(mcp_payload["sign_ins"]), 3)
        self.assertNotIn("TOKEN_ABC", json.dumps(mcp_payload))


if __name__ == "__main__":
    unittest.main()
