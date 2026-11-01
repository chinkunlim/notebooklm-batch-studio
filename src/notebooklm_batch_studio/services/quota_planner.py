"""Quota planning from the live NotebookLM usage meter: pre-checks before a job and workload estimates.

NotebookLM reports, per action kind, whether the account has enough quota and the estimated
cost as a percentage of the five-hour window. This module maps artifact types to those action
kinds so the queue can skip a job before spending a request on it, and so course previews can
estimate how many five-hour windows a workload needs instead of guessing "100 jobs per day".
Refs: ISSUE-008
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.models import ArtifactType
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol

logger = logging.getLogger(__name__)

MIN_RETRY_SECONDS = 60
FIVE_HOUR_WINDOW_HOURS = 5

# Mock exams target ~50 questions, so they usually take two quiz generations.
GENERATIONS_PER_JOB = {
    ArtifactType.COURSE_MOCK_EXAM: 2,
    ArtifactType.COURSE_QUIZ_ACADEMIC: 2,
    ArtifactType.COURSE_QUIZ_CONCEPT: 2,
}

_ACTION_PREFIXES = (
    ("audio", "audio_overview"),
    ("video", "video_overview"),
    ("infographic", "infographic"),
    ("slide_deck", "slides"),
    ("data_table", "tables"),
    ("flashcards", "flashcards"),
    ("mind_map", "mindmap"),
    ("quiz", "quiz"),
    ("mock_exam", "quiz"),
    ("study_guide", "reports"),
    ("reports", "reports"),
)


def action_kind_for(art_type: ArtifactType) -> str | None:
    """Map an artifact type to the NotebookLM usage action kind that it consumes.

    Args:
        art_type: Artifact type of a job.

    Returns:
        Action kind name as reported by the usage meter (e.g. 'audio_overview'), or None.
    """
    value = art_type.value.removeprefix("course_")
    for prefix, kind in _ACTION_PREFIXES:
        if value.startswith(prefix):
            return kind
    return None


def _find_action(quota: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """Find one action entry in a quota summary.

    Args:
        quota: Quota summary from the NotebookLM adapter.
        kind: Action kind name.

    Returns:
        The action dictionary, or None when the meter does not report it.
    """
    return next((a for a in quota.get("actions", []) if a.get("kind") == kind), None)


def quota_retry_after(quota: dict[str, Any], art_type: ArtifactType, now: datetime) -> int | None:
    """Decide whether a job must wait for quota before it is sent to NotebookLM.

    Args:
        quota: Quota summary from the NotebookLM adapter.
        art_type: Artifact type of the job about to run.
        now: Current timezone-aware time.

    Returns:
        Seconds to wait (at least 60) when the meter says quota is insufficient, else None.
    """
    if quota.get("status") != "ready":
        return None
    kind = action_kind_for(art_type)
    action = _find_action(quota, kind) if kind else None
    if action is None or action.get("has_sufficient_quota", True):
        return None
    cost = float(action.get("estimated_cost_percent") or 0.0)
    windows = quota.get("windows", [])
    blocking = [w for w in windows if float(w.get("remaining_percent", 0.0)) < max(cost, 1e-9)]
    resets = [datetime.fromisoformat(w["resets_at"]) for w in (blocking or windows) if w.get("resets_at")]
    if not resets:
        return MIN_RETRY_SECONDS
    return max(MIN_RETRY_SECONDS, math.ceil((max(resets) - now).total_seconds()))


def estimate_quota_plan(types: list[ArtifactType], quota: dict[str, Any] | None) -> dict[str, Any]:
    """Estimate the quota a workload needs, using the live per-action costs.

    Args:
        types: Artifact type of every job in the workload.
        quota: Quota summary from the NotebookLM adapter, or None when it is unavailable.

    Returns:
        Dictionary with `estimated_quota_percent` (of one five-hour window),
        `five_hour_remaining_percent`, `estimated_windows`, `estimated_wait_hours`, and
        `estimated_days`; the numeric fields are None when the meter is unavailable.
    """
    empty: dict[str, Any] = {
        "quota_estimate_available": False,
        "estimated_quota_percent": None,
        "five_hour_remaining_percent": None,
        "estimated_windows": None,
        "estimated_wait_hours": None,
        "estimated_days": None,
    }
    if not quota or quota.get("status") != "ready":
        return empty
    total = 0.0
    for art_type in types:
        kind = action_kind_for(art_type)
        action = _find_action(quota, kind) if kind else None
        cost = float(action.get("estimated_cost_percent") or 0.0) if action else 0.0
        total += cost * GENERATIONS_PER_JOB.get(art_type, 1)
    five_hour = next((w for w in quota.get("windows", []) if w.get("kind") == "five_hour"), None)
    remaining = float(five_hour["remaining_percent"]) if five_hour else 100.0
    extra_windows = math.ceil((total - remaining) / 100.0) if total > remaining else 0
    wait_hours = extra_windows * FIVE_HOUR_WINDOW_HOURS
    return {
        "quota_estimate_available": True,
        "estimated_quota_percent": round(total, 1),
        "five_hour_remaining_percent": round(remaining, 1),
        "estimated_windows": extra_windows + 1,
        "estimated_wait_hours": wait_hours,
        "estimated_days": max(1, math.ceil(wait_hours / 24)),
    }


async def read_quota_or_none(client: NotebookLMClientProtocol) -> dict[str, Any] | None:
    """Read the live usage meter, returning None instead of raising when it is unavailable.

    Args:
        client: NotebookLM client.

    Returns:
        Quota summary, or None.
    """
    try:
        return await client.get_quota_status()
    except Exception as err:  # the meter is advisory; never block work on it
        logger.warning("NotebookLM quota meter unavailable: %s", err)
        return None


async def ensure_quota_for(client: NotebookLMClientProtocol, art_type: ArtifactType) -> None:
    """Refuse to start a job the live meter says cannot be paid for.

    Args:
        client: NotebookLM client.
        art_type: Artifact type of the job about to run.

    Raises:
        QuotaExceededError: When the meter reports insufficient quota for this action.
    """
    quota = await read_quota_or_none(client)
    if quota is None:
        return
    wait = quota_retry_after(quota, art_type, datetime.now(UTC))
    if wait is not None:
        logger.info("Quota pre-check: %s must wait %ds before starting", art_type.value, wait)
        raise QuotaExceededError(
            f"NotebookLM quota insufficient for {art_type.value}",
            artifact_type=art_type.value,
            retry_after_seconds=wait,
        )
