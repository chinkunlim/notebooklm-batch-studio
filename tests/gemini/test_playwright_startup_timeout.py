"""Playwright 啟動逾時保護與重試機制單元測試（note-studio TASK-040 Item 4，note-studio ISSUE-050）。

驗證：
1. BrowserSessionManager 啟動 Playwright 時具備逾時保護（由 config 逾時秒數控制）。
2. 當 node 驅動程式未在時限內完成握手時，僅結束該驅動程式之子程序 (PID)。
3. 逾時後拋出 TimeoutError，並在 log 記明逾時秒數與結束的 PID。
4. 該例外可被 BatchOrchestrator 捕捉並納入章節自動重試流程。
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from notebooklm_batch_studio.adapters.gemini.browser_session import BrowserSessionManager


class PlaywrightStartupTimeoutTest(unittest.TestCase):
    """測試 Playwright 啟動卡住時的超時中斷保護。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_startup_timeout_kills_hanging_driver_process(self) -> None:
        """當 sync_playwright 啟動逾時，看門狗結束該子程序 PID 並拋出 TimeoutError。"""
        # 建立模擬子程序與 PCM
        fake_proc = MagicMock()
        fake_proc.pid = 98765

        fake_transport = MagicMock()
        fake_transport._proc = fake_proc

        fake_conn = MagicMock()
        fake_conn._transport = fake_transport

        mock_pcm = MagicMock()
        mock_pcm._connection = fake_conn
        mock_pcm._playwright = None
        mock_pcm._exit_was_called = False

        # 模擬 start() 阻塞直到子程序被 kill
        def fake_start():
            # 等待看門狗觸發
            for _ in range(50):
                if fake_proc.kill.called or mock_pcm._killed:
                    raise Exception("Connection.init: Connection closed while reading from the driver")
                time.sleep(0.05)
            raise RuntimeError("Fake start did not receive kill")

        mock_pcm._killed = False
        mock_pcm.start.side_effect = fake_start

        # 當看門狗呼叫 os.kill 時標記
        def fake_os_kill(pid, sig):
            if pid == 98765:
                mock_pcm._killed = True
                fake_proc.kill()

        mgr = BrowserSessionManager(
            data_dir=self.data_dir,
            startup_timeout_seconds=1,  # 測試用 1 秒超時
        )

        with patch("playwright.sync_api.sync_playwright", return_value=mock_pcm):
            with patch("os.kill", side_effect=fake_os_kill):
                with self.assertLogs(
                    "notebooklm_batch_studio.adapters.gemini.browser_session", level="ERROR"
                ) as log_cm:
                    with self.assertRaises(TimeoutError) as ctx:
                        with mgr.open_driver(headless=True):
                            pass

        # 驗證拋出清楚的 TimeoutError
        self.assertIn("98765", str(ctx.exception))
        self.assertIn("1 秒內未完成", str(ctx.exception))
        self.assertIn("請重啟網頁伺服器", str(ctx.exception))

        # 驗證記錄了含 PID 的 error log
        log_output = "\n".join(log_cm.output)
        self.assertIn("98765", log_output)
        self.assertIn("timed out after 1s", log_output)
