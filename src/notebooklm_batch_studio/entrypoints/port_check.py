"""Start-up port check for the web server: report who holds a busy port instead of a bare bind error.

The machine-wide port registry is `~/Desktop/projects/00 init_dev_env/PORTS.md`.
"""

from __future__ import annotations

import logging
import socket
import subprocess

logger = logging.getLogger(__name__)


def port_is_free(host: str, port: int) -> bool:
    """Return whether a TCP port can be bound on the given host.

    Args:
        host: Address to bind, e.g. 127.0.0.1.
        port: TCP port.

    Returns:
        True when nothing is listening there.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Same option uvicorn uses: a port left in TIME_WAIT by a server that just stopped is free,
        # while a port with a live listener still fails to bind.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _port_owner(port: int) -> str:
    """Describe the process listening on a port, using lsof when available.

    Args:
        port: TCP port.

    Returns:
        "command (PID n)" lines, or an empty string when unknown.
    """
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired) as err:
        logger.warning("Could not run lsof for port %d: %s", port, err)
        return ""
    rows = [line.split() for line in out.splitlines()[1:] if line.strip()]
    return ", ".join(sorted({f"{r[0]} (PID {r[1]})" for r in rows if len(r) > 1}))


def busy_port_message(host: str, port: int) -> str:
    """Explain, in Chinese, that the port is taken, by whom, and what to do.

    Args:
        host: Address the server wanted.
        port: TCP port.

    Returns:
        A message for the console and the log.
    """
    owner = _port_owner(port) or "未知的程式"
    return (
        f"埠號 {port} 已被 {owner} 使用，網頁伺服器沒有啟動。\n"
        f"如果它就是學習工作室，直接打開 http://{host}:{port} 即可；"
        f"否則請關掉該程式，或在 .env 改用其他 HTTP_PORT"
        "（先查 ~/Desktop/projects/00 init_dev_env/PORTS.md）。"
    )
