"""Shared unconfirmed-guard helper for mutating MCP entrypoint tools."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def confirm_warning(warning: str, **context: Any) -> str:
    """Return standard unconfirmed JSON warning payload for mutating MCP tools.

    Args:
        warning: Action confirmation instruction shown when `confirm=False`.
        **context: Optional identifier fields attached to the payload (e.g. `artifact_id`).

    Returns:
        JSON string `{"confirmed": False, "warning": ..., ...}`.
    """
    logger.debug("MCP confirmation required (%s): %s", list(context.keys()), warning)
    return json.dumps({"confirmed": False, "warning": warning, **context}, ensure_ascii=False)
