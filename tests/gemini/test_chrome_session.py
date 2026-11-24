"""Unit tests for the real-Chrome session helper (note-studio ISSUE-039). No browser is started."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from notebooklm_batch_studio.adapters.gemini import chrome_session
from notebooklm_batch_studio.adapters.gemini.chrome_session import ChromeLaunch


class TestChromeSession(unittest.TestCase):
    """Command line, port discovery and reuse of the running Chrome."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.user_data = Path(self.tmp.name) / "chrome_user_data"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_command_has_no_automation_switch_and_a_real_port(self) -> None:
        """Google rejects sign-in when automation switches or port 0 are used."""
        cmd = chrome_session.chrome_command(ChromeLaunch("/chrome", self.user_data, "https://x/"), 45678)
        self.assertIn("--remote-debugging-port=45678", cmd)
        self.assertIn(f"--user-data-dir={self.user_data}", cmd)
        self.assertEqual(cmd[-1], "https://x/")
        joined = " ".join(cmd)
        for banned in ("--enable-automation", "--remote-debugging-pipe", "--headless", "port=0"):
            self.assertNotIn(banned, joined)

    def test_headless_command_hides_the_headless_user_agent(self) -> None:
        """Headless runs send the ordinary Chrome user agent."""
        with patch.object(chrome_session, "_headless_user_agent", return_value="UA Chrome/157.0.0.0"):
            cmd = chrome_session.chrome_command(ChromeLaunch("/chrome", self.user_data, headless=True), 45678)
        self.assertIn("--headless=new", cmd)
        self.assertIn("--user-agent=UA Chrome/157.0.0.0", cmd)

    def test_running_port_is_none_without_a_port_file(self) -> None:
        """No port file means no Chrome on this profile."""
        self.assertIsNone(chrome_session.running_port(self.user_data))

    def test_running_port_is_none_when_chrome_does_not_answer(self) -> None:
        """A port file left by a closed Chrome is ignored."""
        self.user_data.mkdir(parents=True)
        (self.user_data / chrome_session._PORT_FILE).write_text("45678", encoding="utf-8")
        with patch.object(chrome_session, "_http_json", side_effect=OSError("refused")):
            self.assertIsNone(chrome_session.running_port(self.user_data))

    def test_ensure_chrome_reuses_the_running_chrome(self) -> None:
        """A Chrome already running on the profile is reused, not started twice."""
        self.user_data.mkdir(parents=True)
        (self.user_data / chrome_session._PORT_FILE).write_text("45678", encoding="utf-8")
        with (
            patch.object(chrome_session, "_http_json", return_value={}),
            patch.object(chrome_session.subprocess, "Popen") as popen,
        ):
            port = chrome_session.ensure_chrome(ChromeLaunch("/chrome", self.user_data))
        self.assertEqual(port, 45678)
        popen.assert_not_called()

    def test_ensure_chrome_reports_a_missing_chrome(self) -> None:
        """A wrong Chrome path gives a clear error instead of a hang."""
        launch = ChromeLaunch(str(Path(self.tmp.name) / "no-chrome"), self.user_data)
        with self.assertRaises(RuntimeError):
            chrome_session.ensure_chrome(launch)

    def test_list_tab_urls_keeps_pages_only(self) -> None:
        """Service workers and other targets are not tabs."""
        targets = [
            {"type": "page", "url": "https://gemini.google.com/app"},
            {"type": "service_worker", "url": "https://gemini.google.com/sw.js"},
        ]
        with patch.object(chrome_session, "_http_json", return_value=targets):
            self.assertEqual(chrome_session.list_tab_urls(1), ["https://gemini.google.com/app"])

    def test_acquire_launch_lock_timeout_raises_runtime_error(self) -> None:
        """Lock timeout raises RuntimeError instead of deadlocking (note-studio ISSUE-050)."""
        chrome_session._launch_lock.acquire()
        try:
            with self.assertRaises(RuntimeError):
                with chrome_session._acquire_launch_lock(timeout=0.05):
                    pass
        finally:
            chrome_session._launch_lock.release()

    def test_ensure_chrome_cleans_stale_port_file_when_unresponsive(self) -> None:
        """A stale port file whose Chrome is dead is cleanly removed (note-studio ISSUE-050)."""
        self.user_data.mkdir(parents=True)
        port_file = self.user_data / chrome_session._PORT_FILE
        port_file.write_text("54321", encoding="utf-8")
        with (
            patch.object(chrome_session, "running_port", return_value=None),
            patch.object(chrome_session, "_free_port", return_value=54322),
            patch.object(chrome_session.subprocess, "Popen"),
            patch.object(chrome_session.time, "sleep"),
        ):
            # 模擬第二次 running_port 成功
            def mock_running_port(ud: Path) -> int | None:
                return 54322 if (ud / chrome_session._PORT_FILE).read_text().strip() == "54322" else None

            with patch.object(chrome_session, "running_port", side_effect=mock_running_port):
                port = chrome_session.ensure_chrome(ChromeLaunch("/chrome", self.user_data))
                self.assertEqual(port, 54322)


if __name__ == "__main__":
    unittest.main()
