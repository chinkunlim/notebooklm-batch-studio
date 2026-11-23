"""Real Google Chrome session for Gemini (ISSUE-039).

Google refuses to sign in ("This browser or app may not be secure") inside a
browser that Playwright launched. So Chrome is started here as an ordinary
process with its own user-data folder and a local debugging port. The user signs
in there like in any Chrome; Playwright only attaches to it afterwards.

Main functions:
    ensure_chrome: start Chrome on the profile, or reuse the one already running.
    list_tab_urls: read the open tab addresses without attaching to any page.
    open_tab: open one more tab in the running Chrome.
    quit_chrome: close the Chrome that owns the profile.

Usage:
    port = ensure_chrome(ChromeLaunch(chrome_path, user_data_dir, LOGIN_URL))
    browser = playwright.chromium.connect_over_cdp(cdp_endpoint(port))
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

GEMINI_APP_URL = "https://gemini.google.com/app"
# Starting at the sign-in page means: landing on gemini.google.com proves the sign-in.
LOGIN_URL = "https://accounts.google.com/ServiceLogin?continue=" + urllib.parse.quote(GEMINI_APP_URL, safe="")

# Written here, not by Chrome: Chrome only writes DevToolsActivePort for port 0.
_PORT_FILE = "nbs_gemini_debug_port"
_launch_lock = threading.Lock()
_LAUNCH_LOCK_TIMEOUT_SECONDS = 15.0


@contextmanager
def _acquire_launch_lock(timeout: float = _LAUNCH_LOCK_TIMEOUT_SECONDS) -> Generator[None, None, None]:
    """獲取 Chrome 啟動互斥鎖，具備超時機制防止永久死鎖 (ISSUE-050)。

    Args:
        timeout: 獲取鎖之最長等待秒數。

    Yields:
        None

    Raises:
        RuntimeError: 超時未能獲取啟動鎖時。
    """
    acquired = _launch_lock.acquire(timeout=timeout)
    if not acquired:
        logger.error(
            "Could not acquire Chrome launch lock within %.1f seconds (deadlock detected)",
            timeout,
        )
        msg = f"系統啟動 Chrome 逾時（{timeout:.1f} 秒內無法取得啟動鎖），可能前次仍有背景程序未釋放。"
        raise RuntimeError(msg)
    try:
        yield
    finally:
        _launch_lock.release()


@dataclass(frozen=True)
class ChromeLaunch:
    """How to start Chrome.

    Attributes:
        chrome_path: Google Chrome executable.
        user_data_dir: Folder that keeps this Chrome's profile (the sign-in lives here).
        start_url: Page opened in the first tab.
        headless: Run without a window.
        startup_seconds: Longest wait for Chrome to open its debugging port.
    """

    chrome_path: str
    user_data_dir: Path
    start_url: str = GEMINI_APP_URL
    headless: bool = False
    startup_seconds: float = 30.0


def chrome_user_data_dir(profile_dir: Path) -> Path:
    """Return the Chrome user-data folder kept inside the Gemini profile folder.

    Args:
        profile_dir: DATA_DIR/state/gemini_profile.

    Returns:
        Folder used as Chrome's --user-data-dir.
    """
    return profile_dir / "chrome_user_data"


def cdp_endpoint(port: int) -> str:
    """Return the address Playwright attaches to.

    Args:
        port: Debugging port of the running Chrome.

    Returns:
        Local HTTP address of the debugging port.
    """
    return f"http://127.0.0.1:{port}"


def _http_json(port: int, path: str, method: str = "GET") -> Any:
    """Call Chrome's local debugging HTTP endpoint.

    Args:
        port: Debugging port.
        path: Endpoint path, e.g. "/json/list".
        method: HTTP method ("PUT" is required by /json/new).

    Returns:
        Decoded JSON answer.

    Raises:
        OSError: When Chrome does not answer (not running, or already closed).
    """
    req = urllib.request.Request(cdp_endpoint(port) + path, method=method)
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def running_port(user_data_dir: Path) -> int | None:
    """Find the debugging port of the Chrome that already runs on this profile.

    Args:
        user_data_dir: Chrome user-data folder.

    Returns:
        Port number, or None when no Chrome answers for this profile.
    """
    port_file = user_data_dir / _PORT_FILE
    if not port_file.exists():
        return None
    try:
        port = int(port_file.read_text(encoding="utf-8").splitlines()[0].strip())
        _http_json(port, "/json/version")
        return port
    except (OSError, ValueError, IndexError) as exc:
        logger.info("running_port: no live Chrome behind %s: %s", port_file, exc)
        return None


def _free_port() -> int:
    """Pick a free local port.

    Returns:
        Port number nobody listens on right now.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _headless_user_agent(chrome_path: str) -> str | None:
    """Build the normal Chrome user agent for a headless run.

    Headless Chrome announces itself as "HeadlessChrome", which Google treats as
    a robot; the same version's ordinary name is sent instead.

    Args:
        chrome_path: Google Chrome executable.

    Returns:
        User agent text, or None when the Chrome version cannot be read.
    """
    try:
        out = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [chrome_path, "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout
        major = out.strip().split()[-1].split(".")[0]
        int(major)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        logger.warning("_headless_user_agent: cannot read the Chrome version: %s", exc)
        return None
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


def chrome_command(launch: ChromeLaunch, port: int) -> list[str]:
    """Build the command line that starts Chrome.

    No automation switch is passed: Google's sign-in page rejects browsers that
    carry them. The port is a real number, never 0: with port 0 Chrome marks
    itself as automation-controlled (navigator.webdriver becomes true).

    Args:
        launch: Launch settings.
        port: Local debugging port.

    Returns:
        Argument list for subprocess.
    """
    cmd = [
        launch.chrome_path,
        f"--user-data-dir={launch.user_data_dir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
    ]
    if launch.headless:
        cmd.append("--headless=new")
        user_agent = _headless_user_agent(launch.chrome_path)
        if user_agent:
            cmd.append(f"--user-agent={user_agent}")
    cmd.append(launch.start_url)
    return cmd


def _launch_chrome_process(launch: ChromeLaunch, port: int) -> None:
    """清除舊埠號檔並背景啟動 Chrome 程序，寫入新除錯埠號檔。

    Args:
        launch: Chrome 啟動設定。
        port: 預先分配之除錯埠號。
    """
    launch.user_data_dir.mkdir(parents=True, exist_ok=True)
    stale_file = launch.user_data_dir / _PORT_FILE
    if stale_file.exists():
        try:
            stale_file.unlink()
        except OSError as exc:
            logger.warning("ensure_chrome: removing stale port file failed: %s", exc)
    logger.info("ensure_chrome: starting Chrome on port %d (headless=%s)", port, launch.headless)
    try:
        subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
            chrome_command(launch, port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(f"無法啟動 Google Chrome（{launch.chrome_path}）：{exc}") from exc
    (launch.user_data_dir / _PORT_FILE).write_text(str(port), encoding="utf-8")


def ensure_chrome(launch: ChromeLaunch) -> int:
    """Start Chrome on the profile, or reuse the one already running.

    Args:
        launch: Launch settings.

    Returns:
        Debugging port of the Chrome that owns the profile.

    Raises:
        RuntimeError: When Chrome cannot be started or opens no debugging port in time.
    """
    with _acquire_launch_lock():
        if (port := running_port(launch.user_data_dir)) is not None:
            logger.info("ensure_chrome: reusing Chrome on port %d", port)
            return port
        port = _free_port()
        _launch_chrome_process(launch, port)
        deadline = time.time() + launch.startup_seconds
        while time.time() < deadline:
            if running_port(launch.user_data_dir) == port:
                logger.info("ensure_chrome: Chrome ready on port %d", port)
                return port
            time.sleep(0.3)
        raise RuntimeError("Google Chrome 已啟動，但沒有在時限內開啟本機除錯埠。")


def list_tab_urls(port: int) -> list[str]:
    """Read the addresses of the open tabs without attaching to any page.

    Args:
        port: Debugging port.

    Returns:
        Addresses of the open tabs.

    Raises:
        OSError: When Chrome was closed.
    """
    targets = _http_json(port, "/json/list")
    return [str(t.get("url", "")) for t in targets if t.get("type") == "page"]


def open_tab(port: int, url: str) -> None:
    """Open one more tab in the running Chrome.

    Args:
        port: Debugging port.
        url: Address to open.

    Raises:
        OSError: When Chrome was closed.
    """
    _http_json(port, "/json/new?" + urllib.parse.quote(url, safe=""), method="PUT")


def quit_chrome(browser: Any) -> None:
    """Close the Chrome that Playwright is attached to (the whole application).

    Args:
        browser: Playwright Browser returned by connect_over_cdp.
    """
    try:
        browser.new_browser_cdp_session().send("Browser.close")
        logger.info("quit_chrome: Chrome asked to close")
    except Exception as exc:
        logger.warning("quit_chrome: Chrome did not accept the close request: %s", exc)
