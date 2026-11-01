"""Gemini Notebook quota helpers: turn notebooklm-py usage snapshots into cooldowns and summaries.

Gemini Notebook meters generation in a 5-hour window and a weekly window, each with its own
`resets_at`. These helpers read that live meter instead of guessing a fixed cooldown.
Refs: ISSUE-005
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from notebooklm import UsageSummary

MIN_RETRY_SECONDS = 60


def retry_after_from_usage(usage: UsageSummary, now: datetime) -> int | None:
    """Compute seconds until generation is allowed again, from exhausted usage windows.

    Args:
        usage: Live usage snapshot from `client.settings.get_usage()`.
        now: Current timezone-aware time.

    Returns:
        Seconds until the latest exhausted window resets (at least 60), or None when the
        meter is unavailable or no window is exhausted.
    """
    if not usage.available:
        return None
    exhausted = [w for w in usage.windows if w.remaining_percent <= 0]
    if not exhausted:
        return None
    resets_at = max(w.resets_at for w in exhausted)
    return max(MIN_RETRY_SECONDS, int((resets_at - now).total_seconds()))


def usage_to_dict(usage: UsageSummary) -> dict[str, Any]:
    """Convert a usage snapshot into a JSON-friendly summary for API and MCP responses.

    Args:
        usage: Live usage snapshot from `client.settings.get_usage()`.

    Returns:
        Dictionary with meter status, per-window percentages and reset times, and per-action
        availability.
    """
    return {
        "status": usage.status.value,
        "windows": [
            {
                "kind": w.kind.name.lower(),
                "used_percent": w.used_percent,
                "remaining_percent": w.remaining_percent,
                "resets_at": w.resets_at.isoformat(),
            }
            for w in usage.windows
        ],
        "actions": [
            {
                "kind": a.kind.name.lower() if a.kind else str(a.code),
                "has_sufficient_quota": a.has_sufficient_quota,
                "estimated_cost_percent": a.estimated_cost_percent,
            }
            for a in usage.actions
        ],
    }
