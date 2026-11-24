"""Gemini 瀏覽器會話與 Profile 管理器（note-studio SPEC-012, Plan §9.2）。

以一般方式啟動真正的 Google Chrome（專用 profile 在
DATA_DIR/state/gemini_profile/chrome_user_data/），Playwright 只透過本機除錯埠接上去。
Google 會拒絕在 Playwright 自己啟動的瀏覽器裡登入，所以登入一律在
「Gemini 登入」流程完成（services/notes/gemini_auth_service.py，Refs: ISSUE-053, note-studio ISSUE-039）；
這裡只重用已登入的 profile，不儲存密碼。
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

from notebooklm_batch_studio.adapters.gemini import chrome_session
from notebooklm_batch_studio.adapters.private_dir import ensure_private_dir
from notebooklm_batch_studio.config.settings import load_config
from notebooklm_batch_studio.domain.note_pipeline import PlaywrightStartupTimeoutError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DriverOptions:
    """開啟 Gemini 瀏覽器驅動程式之組態選項。

    Attributes:
        headless: 是否以無外顯視窗模式啟動。
        model: 目標 AI 模型名稱（例如 '4 Argon'）。
        thinking_level: 思考深度名稱。
        auto_close: 是否在會話退出時自動關閉分頁。
        worker_id: 工作緒代號（與共用登入 Chrome 搭配分頁使用）。
        on_done_callback: 工作結束或失敗（在進入保持視窗等待迴圈前）觸發之回呼。
    """

    headless: bool = False
    model: str = ""
    thinking_level: str = ""
    auto_close: bool = False
    worker_id: int = 0
    on_done_callback: Any = None


def _extract_driver_pid(pcm: Any) -> int | None:
    """嘗試自 PlaywrightContextManager 內部連線擷取 Node driver 子程序 PID。

    Args:
        pcm: PlaywrightContextManager 實例。

    Returns:
        Node driver PID，若尚未建立則回傳 None。
    """
    conn = getattr(pcm, "_connection", None)
    transport = getattr(conn, "_transport", None) if conn else None
    proc = getattr(transport, "_proc", None) if transport else None
    return getattr(proc, "pid", None) if proc else None


def _kill_timed_out_driver(pcm: Any, timeout_seconds: int, state: dict[str, Any]) -> None:
    """檢查 Playwright 啟動是否仍卡住，逾時則強制終止驅動子程序。

    Args:
        pcm: PlaywrightContextManager 實例。
        timeout_seconds: 最大等待秒數。
        state: 記錄是否觸發看門狗與已結束 PID 之狀態字典。
    """
    if getattr(pcm, "_playwright", None) is not None or getattr(pcm, "_exit_was_called", False):
        return
    pid = _extract_driver_pid(pcm)
    if not pid:
        return
    state["triggered"] = True
    state["killed_pid"] = pid
    logger.error(
        "Playwright startup timed out after %ds; killing driver process (PID: %d)",
        timeout_seconds,
        pid,
    )
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError as err:
        logger.warning("Failed to kill driver process %d: %s", pid, err)


def _wait_playwright_startup(pcm: Any, timeout_seconds: int, state: dict[str, Any]) -> None:
    """看門狗背景輪詢迴圈：等待 Playwright 啟動完成或逾時觸發終止。

    Args:
        pcm: PlaywrightContextManager 實例。
        timeout_seconds: 最大等待秒數。
        state: 記錄看門狗結果之狀態字典。
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if getattr(pcm, "_playwright", None) is not None or getattr(pcm, "_exit_was_called", False):
            return
        time.sleep(0.05)
    _kill_timed_out_driver(pcm, timeout_seconds, state)


def _start_playwright_with_watchdog(timeout_seconds: int) -> tuple[Any, Any]:
    """啟動 Playwright 並具備驅動程式超時終止保護（note-studio ISSUE-050）。

    Args:
        timeout_seconds: 啟動最大等待秒數。

    Returns:
        (Playwright 實體, PlaywrightContextManager 實體)。

    Raises:
        PlaywrightStartupTimeoutError: 驅動程式未在時限內完成啟動並被終止時。
    """
    from playwright.sync_api import sync_playwright

    pcm = sync_playwright()
    state: dict[str, Any] = {"triggered": False, "killed_pid": None}
    threading.Thread(
        target=_wait_playwright_startup,
        args=(pcm, timeout_seconds, state),
        daemon=True,
    ).start()

    try:
        p = pcm.start()
        return p, pcm
    except Exception as start_err:
        if state["triggered"]:
            killed_pid = state["killed_pid"]
            raise PlaywrightStartupTimeoutError(
                f"Playwright 啟動卡住（{timeout_seconds} 秒內未完成，已結束驅動程式 PID {killed_pid}）。"
                "請重啟網頁伺服器後再繼續生成。"
            ) from start_err
        raise


class BrowserSessionManager:
    """持久化瀏覽器會話管理器。"""

    def __init__(
        self,
        data_dir: Path | None = None,
        startup_timeout_seconds: int | None = None,
        chrome_path: str | None = None,
    ) -> None:
        """初始化會話管理器。

        Args:
            data_dir: 專案 DATA_DIR 路徑；若為 None 則自全域設定讀取。
            startup_timeout_seconds: Playwright 驅動程式啟動超時秒數；若為 None 則自設定讀取。
            chrome_path: Chrome 可執行檔路徑；若為 None 則自設定讀取。
        """
        config = (
            load_config()
            if (data_dir is None or startup_timeout_seconds is None or chrome_path is None)
            else None
        )
        self.data_dir = data_dir if data_dir is not None else config.data_dir  # type: ignore[union-attr]
        self.profile_dir = self.data_dir / "state" / "gemini_profile"
        self.chrome_path = chrome_path if chrome_path is not None else config.chrome_path  # type: ignore[union-attr]
        self.startup_timeout_seconds = (
            startup_timeout_seconds
            if startup_timeout_seconds is not None
            else config.playwright_startup_timeout_seconds  # type: ignore[union-attr]
        )
        logger.debug("BrowserSessionManager initialized with profile at %s", self.profile_dir)

    def get_profile_dir(self) -> Path:
        """取得瀏覽器持久化使用者資料夾路徑。

        Returns:
            Profile 資料夾之絕對路徑。
        """
        ensure_private_dir(self.profile_dir)
        return self.profile_dir

    def get_launch_args(self, headless: bool = True) -> dict[str, Any]:
        """建立 Playwright persistent context 啟動參數。

        Args:
            headless: 是否以無外顯視窗模式啟動。

        Returns:
            啟動組態字典。
        """
        profile_path = self.get_profile_dir()
        args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
        ]
        return {
            "user_data_dir": str(profile_path),
            "headless": headless,
            "args": args,
            "viewport": {"width": 1280, "height": 900},
        }

    def _check_signed_in(self, page: Any) -> bool:
        """檢查頁面是否已處於登入狀態。

        Args:
            page: Playwright Page 物件。

        Returns:
            若已登入回傳 True，若出現 Sign in 相關按鈕回傳 False。
        """
        try:
            sel = (
                'a[href*="accounts.google.com/ServiceLogin"], '
                'a[aria-label*="Sign in"], '
                'a[aria-label*="登入"], '
                'button:has-text("Sign in"), '
                'a:has-text("Sign in"), '
                'a:has-text("登入")'
            )
            sign_in_btn = page.query_selector(sel)
            return sign_in_btn is None
        except Exception as exc:
            logger.warning("_check_signed_in: cannot read the sign-in button; assume signed in: %s", exc)
            return True

    def _sync_storage_state(self, context: Any, target_file: Path) -> None:
        """將最新瀏覽器上下文的憑證與狀態回寫至檔案。

        Args:
            context: Playwright BrowserContext。
            target_file: 憑證檔案路徑。
        """
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(target_file))
            logger.debug("Successfully synced storage state to %s", target_file)
        except Exception as err:
            logger.warning("Storage state sync skipped: %s", err)

    def _resolve_target_profile(self, worker_id: int, storage_state_file: Path) -> Path:
        """解析當前工作線程之 Profile 路徑（多 worker 隔離避免單一鎖定衝突）。

        Args:
            worker_id: 工作緒編號。
            storage_state_file: 主憑證路徑。

        Returns:
            當前工作緒所使用的 Profile 資料夾路徑。
        """
        if worker_id <= 0:
            return self.profile_dir

        target_profile = self.profile_dir.parent / f"gemini_profile_worker_{worker_id}"
        target_profile.mkdir(parents=True, exist_ok=True)
        if storage_state_file.exists():
            import shutil

            shutil.copy2(storage_state_file, target_profile / "storage_state.json")
        return target_profile

    def _verify_page_signed_in(self, browser: Any, context: Any, page: Any) -> None:
        """等待 Gemini 首頁載入並確認使用者已完成登入。

        Args:
            browser: Playwright CDP Browser 實例。
            context: Chrome 預設 BrowserContext。
            page: 已開啟之 Gemini Page 物件。

        Raises:
            RuntimeError: 尚未登入 Gemini 或跳轉至 Google 登入頁時。
        """
        try:
            page.wait_for_timeout(2500)
        except Exception as exc:
            logger.warning("_create_browser_and_page: wait on the page failed (page closed?): %s", exc)
        if "accounts.google.com" not in (page.url or "") and self._check_signed_in(page):
            return
        # Signing in here would be rejected by Google: Playwright is attached (note-studio ISSUE-039).
        self._release(browser, context, page)
        raise RuntimeError(
            "Gemini 尚未登入（或登入已過期）。請先在「筆記生成」頁面按「啟動 Gemini 登入視窗」"
            "（或呼叫 POST /api/notes/gemini/login / MCP 工具 notes_gemini_login），"
            "完成 Google 登入後再重新執行。(Refs: ISSUE-053)"
        )

    def _create_browser_and_page(
        self,
        p: Any,
        headless: bool,
    ) -> tuple[Any, Any, Any]:
        """接上真正的 Chrome 並開一個 Gemini 分頁。

        Args:
            p: Playwright 物件。
            headless: Chrome 尚未執行時，是否以無視窗模式啟動。

        Returns:
            (browser, context, page) 三元組。
        """
        launch = chrome_session.ChromeLaunch(
            chrome_path=self.chrome_path,
            user_data_dir=chrome_session.chrome_user_data_dir(self.profile_dir),
            start_url="about:blank",
            headless=headless,
        )
        port = chrome_session.ensure_chrome(launch)
        browser = p.chromium.connect_over_cdp(chrome_session.cdp_endpoint(port))
        context = browser.contexts[0]
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://gemini.google.com")
        page = context.new_page()
        page.goto(chrome_session.GEMINI_APP_URL, wait_until="domcontentloaded")
        self._verify_page_signed_in(browser, context, page)
        return browser, context, page

    def _release(self, browser: Any, context: Any, page: Any) -> None:
        """關閉本次使用的分頁；沒有其他分頁在用時一併關閉 Chrome。

        Args:
            browser: connect_over_cdp 回傳的 Browser。
            context: Chrome 的預設 BrowserContext。
            page: 本次開的分頁。
        """
        try:
            if not page.is_closed():
                page.close()
            in_use = [pg for pg in context.pages if not pg.is_closed() and pg.url != "about:blank"]
            if not in_use:
                logger.info("_release: no tab in use, closing Chrome")
                chrome_session.quit_chrome(browser)
        except Exception as exc:
            logger.warning("_release: closing the Gemini tab failed: %s", exc)

    def _wait_window_closed(self, page: Any, max_wait_seconds: int = 120) -> None:
        """安全等待瀏覽器視窗手動關閉，具備超時與斷線偵測防止 Worker 死鎖 (note-studio ISSUE-050)。

        Args:
            page: 監聽之 Playwright Page。
            max_wait_seconds: 最長保留等待秒數。
        """
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            try:
                if page.is_closed():
                    break
                page.wait_for_timeout(1000)
            except Exception as exc:
                logger.info("_wait_window_closed: browser disconnected or closed: %s", exc)
                break

    def _init_driver(self, page: Any, opts: DriverOptions) -> Any:
        """建立 GeminiWebDriver 並切換至指定模型與思考深度。

        Args:
            page: Playwright Page 物件。
            opts: 驅動組態選項。

        Returns:
            已初始化之 GeminiWebDriver 實例。
        """
        from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiWebDriver

        driver = GeminiWebDriver(page=page, diagnostic_dir=self.data_dir / "logs")
        if opts.model:
            driver.select_model(opts.model, thinking_level=opts.thinking_level)
        return driver

    def _teardown_driver_session(
        self,
        browser: Any,
        context: Any,
        page: Any,
        opts: DriverOptions,
    ) -> None:
        """保存登入憑證並依無頭或視窗模式釋放或等待分頁關閉。

        Args:
            browser: Playwright CDP Browser 實例。
            context: Chrome BrowserContext。
            page: 本次使用的 Page 物件。
            opts: 驅動組態選項。
        """
        if callable(opts.on_done_callback):
            opts.on_done_callback()
        # Step logs: a batch worker once hung somewhere in this teardown with no trace
        # (note-studio ISSUE-050).
        logger.info("open_driver teardown: saving sign-in state")
        self._sync_storage_state(context, self.profile_dir / "storage_state.json")
        if opts.headless or opts.auto_close:
            logger.info("open_driver teardown: closing the tab")
            self._release(browser, context, page)
            return
        logger.info("視窗模式：任務結束，保持視窗於桌面供檢視（手動關閉或 180 秒後退出）。")
        self._wait_window_closed(page, max_wait_seconds=180)

    @contextmanager
    def open_driver(
        self,
        headless: bool = False,
        model: str = "",
        auto_close: bool = False,
        options: DriverOptions | None = None,
    ) -> Generator[Any, None, None]:
        """接上已登入的真實 Chrome 並產出 GeminiWebDriver 實體。

        Args:
            headless: 是否為無外顯視窗模式（預設 False，使使用者能親眼看見操作）。
            model: 目標 AI 模型名稱（例如 '4 Argon'）。
            auto_close: 是否在會話退出時自動關閉分頁（批次生成為 True；手動模式為 False）。
            options: 進階驅動組態選項；有值時優先覆蓋前列參數。

        Yields:
            GeminiWebDriver 實體。
        """
        opts = options or DriverOptions(headless=headless, model=model, auto_close=auto_close)
        _ = opts.worker_id  # every worker shares the one signed-in Chrome, each in its own tab
        p, pcm = _start_playwright_with_watchdog(self.startup_timeout_seconds)
        try:
            browser, context, page = self._create_browser_and_page(p, opts.headless)
            driver = self._init_driver(page, opts)
            try:
                yield driver
            except Exception as err:
                if not opts.headless and not opts.auto_close:
                    logger.warning("Error occurred during driver session (keeping browser): %s", err)
                raise
            finally:
                self._teardown_driver_session(browser, context, page, opts)
        finally:
            logger.info("open_driver teardown: stopping Playwright")
            pcm.__exit__()
            logger.info("open_driver teardown: done")
