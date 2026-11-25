"""SPEC-021: learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import httpx

from notebooklm_batch_studio.adapters.notebooklm.learning_sites import LearningSiteMixin
from notebooklm_batch_studio.domain.exceptions import AuthExpiredError
from notebooklm_batch_studio.domain.learning_site import SiteRow, parse_site_row
from notebooklm_batch_studio.domain.models import (
    ArtifactType,
    Course,
    Lecture,
    get_artifact_english_title,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.services.artifact_runner import SIMPLE_OUTPUTS
from notebooklm_batch_studio.services.course_settings import COURSE_TYPES
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course
from notebooklm_batch_studio.services.learning_site_prompt import render_site_prompt
from notebooklm_batch_studio.services.quota_planner import action_kind_for

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
FIXTURES = ROOT / "tests" / "fixtures"

LECTURES = [
    Lecture(no=n, topic=f"Topic-{n}", filename=f"Ch{n:02d}.pdf", sha256=str(n), source_id=f"src-{n}")
    for n in (1, 2, 3, 4, 5, 6, 13, 14, 16, 17)
]
LECTURES[0] = replace(LECTURES[0], topic="Career-Counseling-A-Life")
COURSE = Course(code="115-1_CP31000", name="生涯諮商與實務", source_dir="/tmp/x", lectures=LECTURES)


class TypesTest(unittest.TestCase):
    """Task 1: the two new artifact types, their names, files, quota action and web options."""

    def test_types_labels_files_quota_and_ui(self) -> None:
        """Both types have labels, English titles, HTML files, the canvas meter and web options."""
        self.assertEqual(ArtifactType.LEARNING_SITE.value, "learning_site")
        self.assertEqual(ArtifactType.COURSE_LEARNING_SITE.value, "course_learning_site")
        self.assertEqual(label_for("learning_site"), "學習網頁")
        self.assertEqual(label_for("course_learning_site"), "整本書學習網頁")
        self.assertEqual(get_artifact_english_title(ArtifactType.LEARNING_SITE, "L01"), "[L01] Learning Site")
        self.assertEqual(action_kind_for(ArtifactType.LEARNING_SITE), "canvas")
        self.assertEqual(action_kind_for(ArtifactType.COURSE_LEARNING_SITE), "canvas")
        self.assertEqual(
            SIMPLE_OUTPUTS[ArtifactType.LEARNING_SITE][1:],
            ("learning_site.html", "course_learning_site.html"),
        )
        self.assertIn("course_learning_site", COURSE_TYPES)
        js = (STATIC / "studio-queue.js").read_text(encoding="utf-8")
        self.assertIn("{ value: 'learning_site', label: '學習網頁' }", js)
        self.assertIn("{ value: 'course_learning_site', label: '整本書學習網頁' }", js)


class PromptTest(unittest.TestCase):
    """Task 2: prompts come from section A (lecture) or B (whole book) of the bundled template."""

    def test_chapter_prompt_fills_section_a(self) -> None:
        """A lecture prompt starts with the trigger, names the lecture and leaves no placeholder."""
        text = render_site_prompt(COURSE, LECTURES[0])
        self.assertTrue(text.startswith("make me a site"))
        self.assertIn("「生涯諮商與實務」第 1 講「Career Counseling A Life」", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("整本書的互動學習網頁", text)

    def test_book_prompt_uses_section_b_with_range(self) -> None:
        """The whole-book prompt uses section B and states the lecture range and count."""
        text = render_site_prompt(COURSE, None)
        self.assertTrue(text.startswith("make me a site"))
        self.assertIn("整本書的互動學習網頁", text)
        self.assertIn("第 1–17 講（共 10 講）", text)
        self.assertNotIn("{{", text)

    def test_extra_instructions_are_appended(self) -> None:
        """Short custom instructions are appended as 補充要求."""
        text = render_site_prompt(COURSE, LECTURES[0], extra="多舉諮商實例")
        self.assertTrue(text.rstrip().endswith("補充要求：多舉諮商實例"))

    def test_full_custom_prompt_is_used_verbatim(self) -> None:
        """A custom prompt that already starts with the trigger replaces the template."""
        custom = "make me a site\n只做 3 題測驗"
        self.assertEqual(render_site_prompt(COURSE, LECTURES[0], extra=custom), custom)

    def test_planned_site_jobs_have_no_generic_prompt(self) -> None:
        """Planned site jobs carry no generic blueprint, which would otherwise become 補充要求."""
        course = replace(
            COURSE,
            selected_chapter_artifacts=["learning_site"],
            selected_course_artifacts=["course_learning_site"],
        )
        jobs = generate_jobs_for_course(course)
        self.assertEqual(len(jobs), 11)
        self.assertTrue(all(j.custom_prompt is None for j in jobs))


class RowParsingTest(unittest.TestCase):
    """Task 3: raw Studio rows are parsed into SiteRow only for type-10 HTML items."""

    def test_parses_fixture_row(self) -> None:
        """The sanitized real row yields status, file name, URL and creation time."""
        row = json.loads((FIXTURES / "notebooklm" / "site_row.json").read_text(encoding="utf-8"))
        site = parse_site_row(row)
        assert site is not None
        self.assertEqual(site.id, "c493b986-244e-4769-9612-87bcbc2d0ac1")
        self.assertEqual((site.status, site.filename), (3, "生涯諮商：生命生涯發展觀點_互動學習網頁.html"))
        self.assertTrue(site.download_url.startswith("https://contribution.usercontent.google.com/"))
        self.assertAlmostEqual(site.created, 1795595466.808766, places=3)

    def test_generating_row_without_file_is_kept(self) -> None:
        """A type-10 row still generating (no file cell yet) is a site with an empty URL."""
        site = parse_site_row(["new-id", "t", 10, None, 2])
        assert site is not None
        self.assertEqual((site.status, site.download_url), (2, ""))

    def test_non_site_rows_are_ignored(self) -> None:
        """Other Studio types and non-HTML type-10 files are not sites."""
        self.assertIsNone(parse_site_row(["id", "quiz", 4, [], 3]))
        row = ["id", "doc", 10] + [None] * 21 + [["a.pdf", "application/pdf", "", ""]]
        row[4] = 3
        self.assertIsNone(parse_site_row(row))


def _site(url: str = "https://contribution.usercontent.google.com/download?c=1") -> SiteRow:
    """Build a finished SiteRow for download tests.

    Args:
        url: Download URL.

    Returns:
        A done SiteRow.
    """
    return SiteRow(id="s1", title="t", status=3, created=1.0, filename="x.html", download_url=url)


class _FakeAdapter(LearningSiteMixin):
    """LearningSiteMixin with its HTTP layer replaced by an httpx.MockTransport."""

    def __init__(self, handler: object) -> None:
        """Store the mock handler.

        Args:
            handler: Function taking an httpx.Request and returning an httpx.Response.
        """
        self.handler = handler

    def _site_http_client(self) -> httpx.AsyncClient:
        """Return a client whose transport is the mock handler.

        Returns:
            httpx.AsyncClient bound to the mock transport.
        """
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))  # type: ignore[arg-type]


class AdapterTest(unittest.IsolatedAsyncioTestCase):
    """Task 3: the guarded download and the per-notebook lock."""

    def setUp(self) -> None:
        """Create a temp folder for downloads."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "learning_site.html"

    def tearDown(self) -> None:
        """Remove the temp folder."""
        self.tmp.cleanup()

    async def test_download_refuses_non_google_redirect(self) -> None:
        """A redirect leaving Google is refused and nothing is written."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://evil.example/x"})

        with self.assertRaises(ValueError):
            await _FakeAdapter(handler).download_site(_site(), str(self.dest))
        self.assertFalse(self.dest.exists())

    async def test_download_refuses_non_google_start_url(self) -> None:
        """A download URL outside Google is refused before any request."""
        with self.assertRaises(ValueError):
            await _FakeAdapter(lambda r: httpx.Response(200)).download_site(
                _site("https://evil.google.com.example/x"), str(self.dest)
            )

    async def test_download_rejects_sign_in_page(self) -> None:
        """Google's sign-in page means expired auth; nothing is written."""

        def handler(request: httpx.Request) -> httpx.Response:
            body = '<html><a href="https://accounts.google.com/ServiceLogin">x</a></html>'
            return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

        with self.assertRaises(AuthExpiredError):
            await _FakeAdapter(handler).download_site(_site(), str(self.dest))
        self.assertFalse(self.dest.exists())

    async def test_download_writes_html_atomically(self) -> None:
        """A real site (after one Google redirect) is written with no .part file left behind."""
        page = "<!doctype html><title>x</title><p>學習網頁</p>"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "contribution.usercontent.google.com":
                return httpx.Response(302, headers={"location": "https://lh3.googleusercontent.com/f"})
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=page)

        await _FakeAdapter(handler).download_site(_site(), str(self.dest))
        self.assertEqual(self.dest.read_text(encoding="utf-8"), page)
        self.assertEqual([p.name for p in self.dest.parent.iterdir()], ["learning_site.html"])

    async def test_download_rejects_non_html_body(self) -> None:
        """A body that is not HTML is refused."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")

        with self.assertRaises(ValueError):
            await _FakeAdapter(handler).download_site(_site(), str(self.dest))
        self.assertFalse(self.dest.exists())

    async def test_site_requests_are_serialized_per_notebook(self) -> None:
        """The same notebook gets the same lock; different notebooks get different locks."""
        adapter = _FakeAdapter(lambda r: httpx.Response(200))
        self.assertIs(adapter.site_lock("nb1"), adapter.site_lock("nb1"))
        self.assertIsNot(adapter.site_lock("nb1"), adapter.site_lock("nb2"))
        self.assertIsInstance(adapter.site_lock("nb1"), asyncio.Lock)


if __name__ == "__main__":
    unittest.main()
