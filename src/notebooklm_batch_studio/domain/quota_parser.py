"""Gemini quota rate-limit and reset timestamp parser (Refs: ADR-012).

Extracts expected quota reset timestamps from Gemini Web warning banners;
falls back to +1 hour when the banner text cannot be parsed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone, tzinfo

logger = logging.getLogger(__name__)

_DEFAULT_FALLBACK_HOURS = 1


def _parse_relative_time(text: str, now: datetime) -> datetime | None:
    """Parse relative wait duration such as '30 minutes' or '2 小時'.

    Args:
        text: Raw banner text.
        now: Reference UTC datetime.

    Returns:
        Target UTC datetime if matched, otherwise None.
    """
    m_min = re.search(r"(\d+)\s*(?:minutes?|mins?|分鐘)", text, re.IGNORECASE)
    if m_min:
        return now + timedelta(minutes=int(m_min.group(1)))

    m_hour = re.search(r"(\d+)\s*(?:hours?|hrs?|小時)", text, re.IGNORECASE)
    if m_hour:
        return now + timedelta(hours=int(m_hour.group(1)))

    return None


def _parse_time_components(text: str) -> tuple[int, int] | None:
    """Parse (hour, minute) in 24-hour format from banner text.

    Args:
        text: Banner text containing a clock time.

    Returns:
        Tuple of (hour, minute) or None if not found.
    """
    m_zh = re.search(r"(下午|晚上|午後|上午|早上|清晨|凌晨|半夜)\s*(\d{1,2})[:：](\d{2})", text)
    if m_zh:
        period, h_str, m_str = m_zh.group(1), m_zh.group(2), m_zh.group(3)
        hour, minute = int(h_str), int(m_str)
        hour = (hour % 12) + 12 if period in ("下午", "晚上", "午後") else hour % 12
        return hour, minute

    m_en = re.search(r"(\d{1,2})[:：](\d{2})\s*(am|pm)", text, re.IGNORECASE)
    if m_en:
        h_str, m_str, mer = m_en.group(1), m_en.group(2), m_en.group(3).lower()
        hour, minute = int(h_str), int(m_str)
        hour = (hour % 12) + 12 if mer == "pm" else hour % 12
        return hour, minute

    m_24 = re.search(r"(?:於|at|在)?\s*(\d{1,2})[:：](\d{2})", text)
    if m_24:
        hour, minute = int(m_24.group(1)), int(m_24.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    return None


def _resolve_target_datetime(
    time_comp: tuple[int, int],
    text: str,
    now: datetime,
    local_tz: tzinfo | None,
) -> datetime:
    """Convert parsed local clock time to UTC, handling day rollover.

    Args:
        time_comp: Parsed (hour, minute) tuple.
        text: Original banner text for tomorrow/next-day hints.
        now: Reference UTC datetime.
        local_tz: Local timezone; None uses system timezone.

    Returns:
        Target UTC datetime.
    """
    hour, minute = time_comp
    now_local = now.astimezone(local_tz) if local_tz is not None else now.astimezone()
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if re.search(r"tomorrow|明天|次日", text, re.IGNORECASE) or target <= now_local:
        target += timedelta(days=1)

    target_utc = target.astimezone(timezone.utc)
    logger.info("Parsed quota resume time: %s local, %s UTC", target.isoformat(), target_utc)
    return target_utc


def parse_quota_resume_time(
    text: str,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
) -> datetime:
    """Parse expected quota reset time from a Gemini quota warning banner.

    Args:
        text: Raw quota warning text.
        now: Reference UTC datetime (defaults to current UTC time).
        local_tz: Local timezone for clock-time interpretation.

    Returns:
        Parsed or +1 hour fallback UTC datetime.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    raw_text = text if isinstance(text, str) else (str(text) if text is not None else "")
    if not raw_text.strip():
        logger.info("Empty quota text; defaulting to +%d hour fallback", _DEFAULT_FALLBACK_HOURS)
        return now + timedelta(hours=_DEFAULT_FALLBACK_HOURS)

    rel_time = _parse_relative_time(raw_text, now)
    if rel_time is not None:
        return rel_time

    time_comp = _parse_time_components(raw_text)
    if time_comp is None:
        logger.warning("Could not parse quota resume time from '%s'; defaulting to +1h", raw_text)
        return now + timedelta(hours=_DEFAULT_FALLBACK_HOURS)

    return _resolve_target_datetime(time_comp, raw_text, now, local_tz)
