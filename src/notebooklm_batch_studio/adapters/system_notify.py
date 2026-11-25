"""Desktop notification adapter: macOS `osascript` banner, log-only on other platforms (SPEC-017)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

# Text is passed as argv, never spliced into the AppleScript source, so quotes cannot break it.
_SCRIPT = "on run argv\n  display notification (item 2 of argv) with title (item 1 of argv)\nend run"


def send_notification(title: str, message: str) -> bool:
    """Show a desktop notification when supported.

    Args:
        title: Notification title.
        message: Notification body.

    Returns:
        True when the notification command ran successfully.
    """
    osascript = shutil.which("osascript")
    if sys.platform != "darwin" or osascript is None:
        logger.info("Notification (not shown on this platform): %s — %s", title, message)
        return False
    try:
        subprocess.run(
            [osascript, "-e", _SCRIPT, title, message], check=True, timeout=10, capture_output=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Desktop notification failed: %s", exc)
        return False
    logger.info("Desktop notification shown: %s", title)
    return True
