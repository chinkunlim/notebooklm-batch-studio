"""SPEC-022 part 1: Gemini Notebook sign-in through real Chrome (own profile + CDP) on every entry point."""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.notebooklm.chrome_login import ChromeNotebookLoginRuntime
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints import cli
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.notebook_login import LoginInProgressError, NotebookLoginService

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"


class FakeRuntime:
    """Stands in for real Chrome: optionally writes the storage file the way a finished sign-in would."""

    def __init__(self, writes: bool) -> None:
        """Remember whether the fake sign-in succeeds.

        Args:
            writes: Write a storage file (sign-in finished) or not (timeout).
        """
        self.writes = writes
        self.calls: list[tuple[Path, int]] = []

    def run_browser_login(self, storage_state_path: Path, timeout_seconds: int) -> None:
        """Record the call and write the storage file when the sign-in "finishes".

        Args:
            storage_state_path: Where to save the session.
            timeout_seconds: Longest wait.
        """
        self.calls.append((storage_state_path, timeout_seconds))
        if self.writes:
            storage_state_path.write_text('{"cookies": [{"name": "SID"}]}', encoding="utf-8")


class ServiceTest(unittest.TestCase):
    """Saving, verifying, and never clobbering a working session."""

    def setUp(self) -> None:
        """Create a temporary storage path holding an old, working session."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.storage = Path(self.tmpdir.name) / "profiles" / "default" / "storage_state.json"
        self.storage.parent.mkdir(parents=True)
        self.storage.write_text('{"old": true}', encoding="utf-8")

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def test_signed_in_replaces_storage_with_private_permissions(self) -> None:
        """A verified new session replaces the old file with mode 600."""
        runtime = FakeRuntime(writes=True)
        result = NotebookLoginService(self.storage, runtime, lambda p: p.is_file()).login(60)
        self.assertEqual(result["status"], "signed_in")
        self.assertIn("SID", self.storage.read_text(encoding="utf-8"))
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(runtime.calls[0][0], self.storage)  # Chrome writes a temp file first
        self.assertEqual(sorted(p.name for p in self.storage.parent.iterdir()), ["storage_state.json"])

    def test_timeout_keeps_old_storage(self) -> None:
        """No sign-in within the timeout leaves the old session untouched."""
        result = NotebookLoginService(self.storage, FakeRuntime(writes=False), lambda p: True).login(60)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(self.storage.read_text(encoding="utf-8"), '{"old": true}')

    def test_failed_verification_keeps_old_storage(self) -> None:
        """A session that Gemini Notebook rejects is discarded."""
        result = NotebookLoginService(self.storage, FakeRuntime(writes=True), lambda p: False).login(60)
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(self.storage.read_text(encoding="utf-8"), '{"old": true}')
        self.assertEqual(sorted(p.name for p in self.storage.parent.iterdir()), ["storage_state.json"])

    def test_second_login_while_one_runs_is_refused(self) -> None:
        """Only one Chrome sign-in at a time."""
        started, release = threading.Event(), threading.Event()

        class SlowRuntime(FakeRuntime):
            """Blocks inside the sign-in until released."""

            def run_browser_login(self, storage_state_path: Path, timeout_seconds: int) -> None:
                """Block until released.

                Args:
                    storage_state_path: Where to save the session.
                    timeout_seconds: Longest wait.
                """
                started.set()
                release.wait(5)

        service = NotebookLoginService(self.storage, SlowRuntime(writes=False), lambda p: True)
        worker = threading.Thread(target=service.login, args=(60,))
        worker.start()
        started.wait(5)
        with self.assertRaises(LoginInProgressError):
            service.login(60)
        release.set()
        worker.join(5)

    def test_result_never_contains_cookies(self) -> None:
        """Responses carry status and a message only."""
        result = NotebookLoginService(self.storage, FakeRuntime(writes=True), lambda p: True).login(60)
        self.assertNotIn("SID", json.dumps(result))


class RuntimeTest(unittest.TestCase):
    """The Chrome runtime watches notebook.google.com instead of gemini.google.com."""

    def test_start_url_and_signed_in_page(self) -> None:
        """Start page and the signed-in check target Gemini Notebook."""
        runtime = ChromeNotebookLoginRuntime(Path("/tmp/x"), "/chrome")
        self.assertEqual(runtime.start_url, "https://notebook.google.com/")
        page = mock.Mock(url="https://notebook.google.com/notebook/abc")
        self.assertTrue(runtime.is_page_signed_in(page))
        self.assertFalse(runtime.is_page_signed_in(mock.Mock(url="https://accounts.google.com/v3/signin")))
        self.assertFalse(runtime.is_page_signed_in(mock.Mock(url="https://gemini.google.com/app")))

    def test_only_notebook_tabs_trigger_confirmation(self) -> None:
        """A Gemini tab does not count as a finished Gemini Notebook sign-in."""
        runtime = ChromeNotebookLoginRuntime(Path("/tmp/x"), "/chrome")
        with mock.patch.object(runtime, "confirm_signed_in", return_value=True) as confirm:
            self.assertFalse(
                runtime._try_confirm_gemini_tab(1, ["https://gemini.google.com/app"], Path("/s"))
            )
            confirm.assert_not_called()
            with mock.patch("time.sleep"):
                ok = runtime._try_confirm_gemini_tab(1, ["https://notebook.google.com/"], Path("/s"))
            self.assertTrue(ok)

    def test_does_not_open_playwright_browser(self) -> None:
        """Chrome is started with `ensure_chrome` on its own profile, not by Playwright."""
        runtime = ChromeNotebookLoginRuntime(Path("/tmp/nbprofile"), "/chrome")
        with (
            mock.patch(
                "notebooklm_batch_studio.adapters.gemini.chrome_session.ensure_chrome", return_value=9
            ) as ens,
            mock.patch(
                "notebooklm_batch_studio.adapters.gemini.chrome_session.running_port", return_value=None
            ),
            mock.patch("notebooklm_batch_studio.adapters.gemini.auth_runtime.ensure_private_dir"),
            mock.patch.object(runtime, "wait_for_login_completion", return_value=True),
        ):
            runtime.run_browser_login(Path("/tmp/s.json"), 5)
        launch = ens.call_args.args[0]
        self.assertEqual(launch.start_url, "https://notebook.google.com/")
        self.assertIn("nbprofile", str(launch.user_data_dir))


class EntrypointTest(unittest.TestCase):
    """CLI, HTTP, MCP and the sign-in card all use the Chrome sign-in."""

    def setUp(self) -> None:
        """Create an isolated configuration."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name) / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def test_profile_dir_is_under_state(self) -> None:
        """The Chrome profile for Gemini Notebook lives in DATA_DIR/state."""
        self.assertEqual(
            self.cfg.notebooklm_chrome_profile_dir, self.cfg.data_dir / "state" / "notebooklm_chrome_profile"
        )

    def test_http_login_and_conflict(self) -> None:
        """POST /api/notebooklm/login returns the result, and 409 while another sign-in runs."""
        app = create_app(config=self.cfg)
        client = TestClient(app)
        app.state.notebook_login = mock.Mock(
            login=mock.Mock(return_value={"status": "signed_in", "message": "ok"})
        )
        res = client.post("/api/notebooklm/login", json={"timeout_seconds": 60})
        self.assertEqual((res.status_code, res.json()["status"]), (200, "signed_in"))
        app.state.notebook_login.login.assert_called_once_with(60)
        app.state.notebook_login = mock.Mock(login=mock.Mock(side_effect=LoginInProgressError("busy")))
        self.assertEqual(client.post("/api/notebooklm/login", json={}).status_code, 409)

    def test_mcp_tool_requires_confirm(self) -> None:
        """Without confirm the MCP tool explains and does not open Chrome."""
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        with mock.patch(
            "notebooklm_batch_studio.services.notebook_login.NotebookLoginService.login"
        ) as login:
            out = json.loads(tools["notebooklm_login"].fn(timeout_seconds=60))
            login.assert_not_called()
            self.assertFalse(out["confirmed"])

    def test_cli_browser_login_uses_chrome_service(self) -> None:
        """`login --browser` no longer starts `notebooklm login` (Playwright)."""
        service = mock.Mock(login=mock.Mock(return_value={"status": "signed_in", "message": "ok"}))
        with (
            mock.patch.object(cli, "build_notebook_login_service", return_value=service),
            mock.patch("subprocess.call") as sub,
        ):
            code = cli._browser_login(self.cfg, Path(self.tmpdir.name) / "s.json")
        sub.assert_not_called()
        self.assertEqual(code, 0)

    def test_sign_in_card_has_login_button(self) -> None:
        """The Gemini Notebook row on 設計與自訂 has a 登入 button calling the new route."""
        rows = TestClient(create_app(config=self.cfg)).get("/api/system/sign-ins").json()["sign_ins"]
        self.assertEqual(rows[0]["login_route"], "/api/notebooklm/login")
        self.assertIn("'/api/notebooklm/login'", (STATIC / "studio-record.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
