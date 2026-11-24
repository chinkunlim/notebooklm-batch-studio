"""Create browser-profile folders that only the current user can read (Refs: ADR-013).

Chrome / Playwright profiles hold signed-in Google and library session cookies, so they are
created (or tightened) with mode 700 instead of the default umask (usually 755).
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

# Owner read / write / execute only.
PRIVATE_DIR_MODE = 0o700


def ensure_private_dir(path: Path) -> Path:
    """Create `path` if needed and restrict it to the current user (mode 700).

    Args:
        path: Folder holding browser profile data.

    Returns:
        The same path, now existing with private permissions.
    """
    path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIR_MODE)
    current = stat.S_IMODE(path.stat().st_mode)
    if current != PRIVATE_DIR_MODE:
        try:
            os.chmod(path, PRIVATE_DIR_MODE)
            logger.info("Restricted browser profile folder permissions to 700: %s", path)
        except OSError as exc:
            logger.warning("Could not restrict permissions of %s: %s", path, exc)
    return path
