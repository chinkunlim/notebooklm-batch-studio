"""Unit and integration tests for GeminiAuthService, HTTP routes, and MCP tools (Refs: ISSUE-053)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.gemini.auth_runtime import ChromeGeminiLoginRuntime
from notebooklm_batch_studio.adapters.gemini.browser_session import BrowserSessionManager
from notebooklm_batch_studio.adapters.note_driver_factory import build_gemini_auth_service
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.notes.gemini_auth_service import GeminiAuthService


class TestGeminiAuthService(unittest.TestCase):
    """Test GeminiAuthService authentication checks, Chrome runtime, and session management."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.service = build_gemini_auth_service(
            AppConfig(
                app_env="test",
                log_to_file=False,
                data_dir=self.data_dir,
                database_url=f"sqlite:///{self.data_dir / 'app.db'}",
            )
        )
        self.runtime = ChromeGeminiLoginRuntime(
            profile_dir=self.service.profile_dir,
            chrome_path=self.service.chrome_path,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_auth_status_when_no_session(self) -> None:
        """When no storage_state exists, auth status is not logged in."""
        status = self.service.check_auth_status()
        self.assertFalse(status["logged_in"])
        self.assertEqual(status["cookie_count"], 0)
        self.assertEqual(status["updated_at"], "")

    def test_auth_status_with_valid_session(self) -> None:
        """When storage_state contains valid google cookies, status is logged in."""
        state_file = self.service.get_storage_state_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        fake_state = {
            "cookies": [
                {
                    "name": "SID",
                    "value": "fake_sid_token_12345",
                    "domain": ".google.com",
                    "path": "/",
                    "expires": 1893456000,
                },
                {
                    "name": "SSID",
                    "value": "fake_ssid_token_67890",
                    "domain": ".google.com",
                    "path": "/",
                    "expires": 1893456000,
                },
            ],
            "origins": [],
        }
        state_file.write_text(json.dumps(fake_state), encoding="utf-8")

        status = self.service.check_auth_status()
        self.assertTrue(status["logged_in"])
        self.assertEqual(status["cookie_count"], 2)
        self.assertNotEqual(status["updated_at"], "")

    def test_logout_clears_session(self) -> None:
        """Calling logout deletes storage state and sets auth status to logged out."""
        state_file = self.service.get_storage_state_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        fake_state = {
            "cookies": [{"name": "SID", "domain": ".google.com", "expires": 1893456000}],
            "origins": [],
        }
        state_file.write_text(json.dumps(fake_state), encoding="utf-8")

        self.assertTrue(self.service.check_auth_status()["logged_in"])
        result = self.service.logout()
        self.assertTrue(result["success"])
        self.assertFalse(result["logged_in"])
        self.assertFalse(state_file.exists())
        self.assertFalse(self.service.check_auth_status()["logged_in"])

    def test_auth_status_with_corrupt_file(self) -> None:
        """When storage_state contains invalid JSON, handles gracefully."""
        state_file = self.service.get_storage_state_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("not-a-valid-json", encoding="utf-8")

        status = self.service.check_auth_status()
        self.assertFalse(status["logged_in"])

    def test_has_auth_cookies_detection(self) -> None:
        """Context cookies are verified for google domain and auth names."""
        fake_context = MagicMock()
        fake_context.cookies.return_value = [
            {"name": "NID", "domain": ".google.com", "expires": 2000000000},
            {"name": "_ga", "domain": ".gemini.google.com", "expires": 2000000000},
        ]
        self.assertFalse(self.runtime.has_auth_cookies(fake_context))

        fake_context.cookies.return_value.append(
            {"name": "SID", "domain": ".google.com", "expires": 2000000000}
        )
        self.assertTrue(self.runtime.has_auth_cookies(fake_context))

    def test_wait_for_login_never_attaches_during_google_sign_in(self) -> None:
        """While the tab is on accounts.google.com nothing attaches to Chrome (note-studio ISSUE-039)."""
        import time

        login_tab = ["https://accounts.google.com/v3/signin/identifier?continue=x"]
        with (
            patch(
                "notebooklm_batch_studio.adapters.gemini.auth_runtime.chrome_session.list_tab_urls",
                return_value=login_tab,
            ),
            patch.object(self.runtime, "confirm_signed_in") as confirm,
        ):
            start = time.time()
            done = self.runtime.wait_for_login_completion(
                port=1, storage_state_path=self.service.storage_state_path, timeout_seconds=1
            )
        self.assertFalse(done)
        self.assertGreaterEqual(time.time() - start, 0.9)
        confirm.assert_not_called()

    def test_wait_for_login_confirms_once_back_on_gemini(self) -> None:
        """A tab back on gemini.google.com triggers the sign-in check and ends the wait."""
        tabs = ["https://gemini.google.com/app"]
        state_path = self.service.storage_state_path
        with (
            patch(
                "notebooklm_batch_studio.adapters.gemini.auth_runtime.chrome_session.list_tab_urls",
                return_value=tabs,
            ),
            patch("notebooklm_batch_studio.adapters.gemini.auth_runtime.time.sleep"),
            patch.object(self.runtime, "confirm_signed_in", return_value=True) as confirm,
        ):
            self.assertTrue(
                self.runtime.wait_for_login_completion(
                    port=1, storage_state_path=state_path, timeout_seconds=30
                )
            )
        confirm.assert_called_once_with(1, state_path)

    def test_wait_for_login_stops_when_chrome_is_closed(self) -> None:
        """Closing Chrome ends the wait without a confirmed sign-in."""
        with patch(
            "notebooklm_batch_studio.adapters.gemini.auth_runtime.chrome_session.list_tab_urls",
            side_effect=OSError("connection refused"),
        ):
            self.assertFalse(
                self.runtime.wait_for_login_completion(
                    port=1, storage_state_path=self.service.storage_state_path, timeout_seconds=30
                )
            )

    def test_page_signed_in_needs_avatar_and_no_sign_in_link(self) -> None:
        """The guest Gemini page (Sign in link present) is not a signed-in page (note-studio ISSUE-025)."""
        page = MagicMock()
        page.url = "https://gemini.google.com/app"
        page.query_selector.side_effect = lambda sel: MagicMock() if "ServiceLogin" in sel else None
        self.assertFalse(self.runtime.is_page_signed_in(page))
        page.query_selector.side_effect = lambda sel: None if "ServiceLogin" in sel else MagicMock()
        self.assertTrue(self.runtime.is_page_signed_in(page))

    def test_logout_removes_the_chrome_profile(self) -> None:
        """Logout deletes the Chrome profile, where the sign-in really lives."""
        from notebooklm_batch_studio.adapters.gemini import chrome_session

        chrome_dir = chrome_session.chrome_user_data_dir(self.service.profile_dir)
        (chrome_dir / "Default").mkdir(parents=True)
        result = self.service.logout()
        self.assertTrue(result["success"])
        self.assertFalse(chrome_dir.exists())

    def test_live_probe_failure_preserves_storage_state(self) -> None:
        """Verify transient live probe failure does not delete storage_state file (note-studio ISSUE-030)."""
        state_file = self.service.get_storage_state_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        valid_data = {
            "cookies": [
                {
                    "name": "SID",
                    "value": "valid_token",
                    "domain": ".google.com",
                    "path": "/",
                    "expires": 2000000000,
                }
            ],
            "origins": [],
        }
        state_file.write_text(json.dumps(valid_data), encoding="utf-8")

        with patch.object(self.service, "verify_live_session", return_value=False):
            status = self.service.check_auth_status(live_check=True)

        self.assertFalse(status["logged_in"])
        self.assertEqual(status["reason"], "session_invalidated")
        self.assertTrue(
            state_file.exists(),
            "Storage state file must be preserved on transient probe failure (note-studio ISSUE-030).",
        )


class TestGeminiAuthIntegration(unittest.TestCase):
    """Test HTTP API, MCP Server, UI buttons, and error guidance for Gemini Web Auth (ISSUE-053)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.config = AppConfig(
            app_env="test",
            log_to_file=False,
            data_dir=self.data_dir,
            database_url=f"sqlite:///{self.data_dir / 'app.db'}",
            http_host="127.0.0.1",
            http_port=8768,
            http_allowed_origins=("http://127.0.0.1:8768",),
        )
        self.app = create_app(config=self.config)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8768")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_http_auth_status_route(self) -> None:
        """GET /api/notes/gemini/auth-status returns current authentication status."""
        resp = self.client.get("/api/notes/gemini/auth-status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("logged_in", data)
        self.assertFalse(data["logged_in"])

    def test_http_login_route_mocked(self) -> None:
        """POST /api/notes/gemini/login triggers interactive login via service."""
        with patch.object(
            GeminiAuthService,
            "login_interactive",
            return_value={
                "success": True,
                "logged_in": True,
                "message": "Gemini 登入成功並已儲存會話。",
                "updated_at": "2026-11-24T10:00:00Z",
            },
        ):
            resp = self.client.post("/api/notes/gemini/login", json={"timeout_seconds": 60})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertTrue(data["logged_in"])

    def test_http_logout_route(self) -> None:
        """POST /api/notes/gemini/logout requires confirm: true and deletes session."""
        refuse_res = self.client.post("/api/notes/gemini/logout", json={})
        self.assertEqual(refuse_res.status_code, 200)
        self.assertFalse(refuse_res.json()["success"])

        ok_res = self.client.post("/api/notes/gemini/logout", json={"confirm": True})
        self.assertEqual(ok_res.status_code, 200)
        self.assertTrue(ok_res.json()["success"])
        self.assertFalse(ok_res.json()["logged_in"])

    def test_http_retention_route(self) -> None:
        """POST /api/notes/gemini/retention configures cookie retention days."""
        resp = self.client.post("/api/notes/gemini/retention", json={"retention_days": 14})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["success"])

        resp2 = self.client.post("/api/notes/gemini/retention", json={"retention_days": 14, "confirm": True})
        self.assertEqual(resp2.status_code, 200)
        data = resp2.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["retention_days"], 14)

        status_resp = self.client.get("/api/notes/gemini/auth-status")
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["retention_days"], 14)

    def test_mcp_gemini_auth_tools(self) -> None:
        """MCP server exposes notes_gemini_* tools with confirm=True guards on mutations."""
        mcp = build_mcp_server(config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        for expected in (
            "notes_gemini_auth_status",
            "notes_gemini_login",
            "notes_gemini_logout",
            "notes_set_gemini_retention",
        ):
            self.assertIn(expected, tools)

        status = json.loads(tools["notes_gemini_auth_status"].fn())
        self.assertFalse(status["logged_in"])

        for call in (
            tools["notes_gemini_login"].fn(),
            tools["notes_gemini_logout"].fn(),
            tools["notes_set_gemini_retention"].fn(14),
        ):
            payload = json.loads(call)
            self.assertFalse(payload["confirmed"])
            self.assertIn("warning", payload)

    def test_browser_session_error_points_to_real_entrypoints(self) -> None:
        """Signed-out error message and Web UI point to real notebooklm-batch-studio entrypoints."""
        mgr = BrowserSessionManager(
            data_dir=self.data_dir,
            startup_timeout_seconds=10,
            chrome_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        fake_page = MagicMock()
        fake_page.url = "https://accounts.google.com/v3/signin/rejected"
        with patch.object(mgr, "_release"), self.assertRaises(RuntimeError) as ctx:
            mgr._verify_page_signed_in(MagicMock(), MagicMock(), fake_page)

        msg = str(ctx.exception)
        self.assertIn("啟動 Gemini 登入視窗", msg)
        self.assertIn("notes_gemini_login", msg)
        self.assertNotIn("note_studio_gemini_login", msg)

        static_dir = (
            Path(__file__).resolve().parent.parent.parent / "src/notebooklm_batch_studio/entrypoints/static"
        )
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        js = (static_dir / "studio-notes-gen.js").read_text(encoding="utf-8")
        self.assertIn("btnGeminiLogin", html)
        self.assertIn("/api/notes/gemini/login", js)


if __name__ == "__main__":
    unittest.main()
