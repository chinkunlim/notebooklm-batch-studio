"""Run one learning-site job: chat request → wait for the new Studio site → download (SPEC-021).

Gemini Notebook does not say which request produced which Studio item, so the runner snapshots
the existing sites, sends the prompt under a per-notebook lock, and takes the newest site that was
not there before.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.learning_site import (
    STATUS_DONE,
    STATUS_GENERATING,
    LearningSiteClientProtocol,
    SiteRow,
)
from notebooklm_batch_studio.domain.models import ArtifactJob, Course
from notebooklm_batch_studio.domain.naming import versioned_name
from notebooklm_batch_studio.services.learning_site_prompt import render_site_prompt
from notebooklm_batch_studio.services.quiz_runner import JobTarget, ProcessResult

logger = logging.getLogger(__name__)

APPEAR_SECONDS = 300
FINISH_SECONDS = 1800
POLL_SECONDS = 20
QUOTA_WORDS = ("額度", "上限", "quota", "limit")
LECTURE_FILE = "learning_site.html"
COURSE_FILE = "course_learning_site.html"


def _no_site_error(answer: str, job: ArtifactJob) -> Exception:
    """Explain why no site appeared after the request.

    Args:
        answer: Gemini Notebook's chat answer to the prompt.
        job: The site job.

    Returns:
        QuotaExceededError when the answer mentions quota, else RuntimeError carrying the answer.
    """
    lowered = answer.lower()
    if any(word in lowered for word in QUOTA_WORDS):
        return QuotaExceededError(
            f"Gemini Notebook 沒有開始產生學習網頁（疑似額度用完）：{answer[:300]}",
            artifact_type=job.artifact_type.value,
        )
    return RuntimeError(f"Gemini Notebook 沒有開始產生學習網頁，回覆：{answer[:500]}")


class LearningSiteRunner:
    """Produce learning-site files through a `LearningSiteClientProtocol`."""

    def __init__(
        self,
        client: LearningSiteClientProtocol,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Store the client and the clock used for polling.

        Args:
            client: Gemini Notebook adapter implementing the site protocol.
            clock: Monotonic clock in seconds (tests pass a fake).
            sleep: Async sleep (tests pass one that advances the fake clock).
        """
        self.client = client
        self.clock = clock
        self.sleep = sleep

    async def process(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate and download one learning site.

        Args:
            job: Site job (`learning_site` with a lecture, or `course_learning_site`).
            course: Course the job belongs to.
            target: Notebook, ticked sources and output folder.

        Returns:
            Saved HTML path and the Studio id of the site.
        """
        lecture = next((lec for lec in course.lectures if lec.no == job.lecture_no), None)
        prompt = render_site_prompt(
            course, lecture if job.lecture_no is not None else None, extra=job.custom_prompt
        )
        name = LECTURE_FILE if job.lecture_no is not None else COURSE_FILE
        out_file = target.out_dir / versioned_name(name, job.version)
        async with self.client.site_lock(target.nb_id):
            before = {row.id for row in await self.client.list_site_rows(target.nb_id)}
            answer = await self.client.request_site(target.nb_id, prompt, target.source_ids)
            logger.info("learning site requested job=%s answer_chars=%d", job.id, len(answer))
            site = await self._wait_for_new_site(target.nb_id, before, answer, job)
            site = await self._wait_until_done(target.nb_id, site.id)
            Path(target.out_dir).mkdir(parents=True, exist_ok=True)
            await self.client.download_site(site, str(out_file))
        logger.info("learning site saved job=%s site=%s path=%s", job.id, site.id, out_file)
        return str(out_file), [site.id]

    async def _wait_for_new_site(
        self, nb_id: str, before: set[str], answer: str, job: ArtifactJob
    ) -> SiteRow:
        """Poll Studio until a site that was not there before appears.

        Args:
            nb_id: Notebook identifier.
            before: Site ids present before the request.
            answer: Chat answer (explains a missing site).
            job: The site job.

        Returns:
            The newest new site row.

        Raises:
            QuotaExceededError: No site within APPEAR_SECONDS and the answer mentions quota.
            RuntimeError: No site within APPEAR_SECONDS for any other reason.
        """
        deadline = self.clock() + APPEAR_SECONDS
        while True:
            new = [row for row in await self.client.list_site_rows(nb_id) if row.id not in before]
            if new:
                return max(new, key=lambda row: row.created)
            if self.clock() >= deadline:
                logger.warning("no learning site appeared job=%s", job.id)
                raise _no_site_error(answer, job)
            await self.sleep(POLL_SECONDS)

    async def _wait_until_done(self, nb_id: str, site_id: str) -> SiteRow:
        """Poll Studio until the site is finished.

        Args:
            nb_id: Notebook identifier.
            site_id: Studio id of the new site.

        Returns:
            The finished site row (with a download URL).

        Raises:
            RuntimeError: When the site fails, disappears, has no URL, or exceeds FINISH_SECONDS.
        """
        deadline = self.clock() + FINISH_SECONDS
        while True:
            row = next((r for r in await self.client.list_site_rows(nb_id) if r.id == site_id), None)
            if row is None or row.status not in (STATUS_GENERATING, STATUS_DONE):
                raise RuntimeError(
                    f"學習網頁產生失敗（site={site_id}, status={row.status if row else 'gone'}）"
                )
            if row.status == STATUS_DONE:
                if not row.download_url:
                    raise RuntimeError(f"學習網頁已完成但沒有下載網址（site={site_id}）")
                return row
            if self.clock() >= deadline:
                raise RuntimeError(f"學習網頁超過 {FINISH_SECONDS} 秒仍未完成（site={site_id}）")
            await self.sleep(POLL_SECONDS)
