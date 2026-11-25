"""SPEC-021: learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.notebooklm.learning_sites import LearningSiteMixin
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import AuthExpiredError, QuotaExceededError
from notebooklm_batch_studio.domain.learning_site import SiteRow, parse_site_row
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    Lecture,
    get_artifact_english_title,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.http.learning_site import SITE_CSP, STORAGE_SHIM_MARKER
from notebooklm_batch_studio.services.artifact_runner import SIMPLE_OUTPUTS, ArtifactRunner
from notebooklm_batch_studio.services.course_settings import COURSE_TYPES
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course
from notebooklm_batch_studio.services.learning_site_prompt import render_site_prompt
from notebooklm_batch_studio.services.learning_site_runner import APPEAR_SECONDS, LearningSiteRunner
from notebooklm_batch_studio.services.quiz_runner import JobTarget
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


class _FakeSiteClient:
    """Scripted LearningSiteClientProtocol: each list call returns the next scripted listing."""

    def __init__(self, listings: list[list[SiteRow]], answer: str = "已為您送出生成請求") -> None:
        """Store the scripted listings and chat answer.

        Args:
            listings: Studio listings returned in order (the last one repeats).
            answer: Chat answer returned by request_site.
        """
        self.listings = listings
        self.answer = answer
        self.requests: list[tuple[str, str, list[str]]] = []
        self.downloads: list[tuple[str, str]] = []
        self.locks: dict[str, asyncio.Lock] = {}

    async def list_site_rows(self, notebook_id: str) -> list[SiteRow]:
        """Return the next scripted listing.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Site rows.
        """
        return self.listings.pop(0) if len(self.listings) > 1 else self.listings[0]

    async def request_site(self, notebook_id: str, prompt: str, source_ids: list[str]) -> str:
        """Record the request.

        Args:
            notebook_id: Notebook identifier.
            prompt: Prompt text.
            source_ids: Ticked sources.

        Returns:
            The scripted answer.
        """
        self.requests.append((notebook_id, prompt, source_ids))
        return self.answer

    async def download_site(self, row: SiteRow, output_path: str) -> None:
        """Record the download and write a stub file.

        Args:
            row: Site row.
            output_path: Destination.
        """
        self.downloads.append((row.id, output_path))
        Path(output_path).write_text("<!doctype html>", encoding="utf-8")

    def site_lock(self, notebook_id: str) -> asyncio.Lock:
        """Return a per-notebook lock.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Lock.
        """
        return self.locks.setdefault(notebook_id, asyncio.Lock())


def _row(site_id: str, status: int, created: float = 1.0, url: str = "https://x.google.com/d") -> SiteRow:
    """Build a SiteRow for runner tests.

    Args:
        site_id: Studio id.
        status: Raw status.
        created: Creation time.
        url: Download URL.

    Returns:
        SiteRow.
    """
    return SiteRow(id=site_id, title="t", status=status, created=created, filename="a.html", download_url=url)


class RunnerTest(unittest.IsolatedAsyncioTestCase):
    """Task 4: request → wait for a new Studio site → wait until done → download."""

    def setUp(self) -> None:
        """Create a temp output folder, a fake clock and a lecture-1 site job."""
        self.tmp = tempfile.TemporaryDirectory()
        self.target = JobTarget(nb_id="nb1", source_ids=["src-1"], out_dir=Path(self.tmp.name))
        self.now = 0.0
        self.job = ArtifactJob(
            id="j1",
            course_code=COURSE.code,
            lecture_no=1,
            artifact_type=ArtifactType.LEARNING_SITE,
            version=2,
        )

    def tearDown(self) -> None:
        """Remove the temp folder."""
        self.tmp.cleanup()

    def _clock(self) -> float:
        """Fake monotonic clock.

        Returns:
            Current fake time.
        """
        return self.now

    async def _sleep(self, seconds: float) -> None:
        """Advance the fake clock instead of sleeping.

        Args:
            seconds: Time to advance.
        """
        self.now += seconds

    def _runner(self, client: _FakeSiteClient) -> LearningSiteRunner:
        """Build a runner on the fake clock.

        Args:
            client: Fake site client.

        Returns:
            LearningSiteRunner.
        """
        return LearningSiteRunner(client, clock=self._clock, sleep=self._sleep)

    async def test_downloads_new_site_to_versioned_file(self) -> None:
        """The new site (not the old one) is awaited until done and saved as learning_site_v2.html."""
        old = _row("old", 3)
        client = _FakeSiteClient([[old], [old], [old, _row("new", 2, 5.0)], [old, _row("new", 3, 5.0)]])
        path, ids = await self._runner(client).process(self.job, COURSE, self.target)
        self.assertEqual(Path(path), self.target.out_dir / "learning_site_v2.html")
        self.assertEqual(ids, ["new"])
        self.assertEqual(client.downloads, [("new", path)])
        nb_id, prompt, sources = client.requests[0]
        self.assertEqual((nb_id, sources), ("nb1", ["src-1"]))
        self.assertTrue(prompt.startswith("make me a site"))

    async def test_course_site_uses_course_file_name(self) -> None:
        """A whole-book job is saved as course_learning_site.html."""
        job = replace(self.job, lecture_no=None, artifact_type=ArtifactType.COURSE_LEARNING_SITE, version=1)
        client = _FakeSiteClient([[], [_row("new", 3)]])
        path, _ = await self._runner(client).process(job, COURSE, self.target)
        self.assertEqual(Path(path).name, "course_learning_site.html")
        self.assertIn("整本書的互動學習網頁", client.requests[0][1])

    async def test_no_new_site_with_quota_words_raises_quota(self) -> None:
        """No new site within APPEAR_SECONDS and a quota-like answer → QuotaExceededError."""
        client = _FakeSiteClient([[_row("old", 3)]], answer="目前已達使用上限，請稍後再試")
        with self.assertRaises(QuotaExceededError):
            await self._runner(client).process(self.job, COURSE, self.target)
        self.assertGreaterEqual(self.now, APPEAR_SECONDS)
        self.assertEqual(client.downloads, [])

    async def test_no_new_site_raises_generation_error(self) -> None:
        """No new site and any other answer → RuntimeError carrying the answer."""
        client = _FakeSiteClient([[]], answer="我無法建立網站")
        with self.assertRaises(RuntimeError) as ctx:
            await self._runner(client).process(self.job, COURSE, self.target)
        self.assertIn("我無法建立網站", str(ctx.exception))

    async def test_failed_status_raises(self) -> None:
        """A new site that ends in a failure status → RuntimeError, nothing downloaded."""
        client = _FakeSiteClient([[], [_row("new", 2)], [_row("new", 4)]])
        with self.assertRaises(RuntimeError):
            await self._runner(client).process(self.job, COURSE, self.target)
        self.assertEqual(client.downloads, [])

    async def test_artifact_runner_dispatches_and_renames(self) -> None:
        """ArtifactRunner sends site jobs to its site runner, then gives the Studio item the standard title.

        Gemini Notebook stores a site's title as a file name ("[Ch01]_Learning_Site_(v2).html"),
        which still starts with the lecture prefix like every other output.
        """
        client = _FakeSiteClient([[], [_row("new", 3)]])
        client.rename_artifact = mock.AsyncMock()  # type: ignore[attr-defined]
        runner = ArtifactRunner(client, mock.Mock())  # type: ignore[arg-type]
        runner.site_runner = self._runner(client)
        path, ids = await runner.process_job_with_ids(self.job, COURSE, self.target)
        self.assertEqual((Path(path).name, ids), ("learning_site_v2.html", ["new"]))
        client.rename_artifact.assert_awaited_once_with("nb1", "new", "[Ch01] Learning Site (v2)")  # type: ignore[attr-defined]


EXPECTED_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
    "font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; "
    "frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads"
)


class ViewTest(unittest.TestCase):
    """Task 5: generated sites open only through a sandboxed, CSP-restricted route."""

    def setUp(self) -> None:
        """Create a course with one downloaded learning site."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name) / "data"
        cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        cfg.ensure_data_dirs()
        self.engine = create_db_engine(cfg.database_url)
        Base.metadata.create_all(self.engine)
        course_dir = cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        lec_dir = course_dir / "03 Notes" / "NotebookLM" / "01_x"
        lec_dir.mkdir(parents=True)
        (lec_dir / "learning_site.html").write_text(
            "<!doctype html><html><head><title>t</title></head><body>學習網頁</body></html>", encoding="utf-8"
        )
        (lec_dir / "infographic.png").write_bytes(b"\x89PNG")
        with make_session_factory(self.engine)() as session:
            CourseRepository(session).save_course(
                Course(
                    code=COURSE.code, name=COURSE.name, source_dir=str(course_dir), study_dir=str(course_dir)
                )
            )
            session.commit()
        self.client = TestClient(create_app(config=cfg))
        self.base = f"/api/artifacts/{COURSE.code}"

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_site_route_sets_strict_csp(self) -> None:
        """The site is served as HTML with the exact sandboxing CSP and the storage adapter injected."""
        self.assertEqual(SITE_CSP, EXPECTED_CSP)
        res = self.client.get(f"{self.base}/site/01_x/learning_site.html")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.headers["content-security-policy"], EXPECTED_CSP)
        self.assertEqual(res.headers["x-content-type-options"], "nosniff")
        self.assertEqual(res.headers["referrer-policy"], "no-referrer")
        self.assertTrue(res.headers["content-type"].startswith("text/html"))
        body = res.text
        self.assertIn(STORAGE_SHIM_MARKER, body)
        self.assertIn("學習網頁", body)
        self.assertLess(body.index(STORAGE_SHIM_MARKER), body.index("<title>"))

    def test_site_route_rejects_non_html_and_traversal(self) -> None:
        """Non-HTML files get 415; traversal outside the course folder gets 403."""
        self.assertEqual(self.client.get(f"{self.base}/site/01_x/infographic.png").status_code, 415)
        # %2F keeps the dots inside the path parameter (a client would collapse a literal "../")
        traversal = f"{self.base}/site/01_x/..%2F..%2F..%2F..%2F..%2F..%2Fx.html"
        self.assertEqual(self.client.get(traversal).status_code, 403)

    def test_download_route_attaches_learning_site(self) -> None:
        """The plain download route never serves a learning site inline on the app origin."""
        res = self.client.get(f"{self.base}/download/01_x/learning_site.html")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-disposition"].startswith("attachment"))

    def test_study_workspace_opens_site_route_sandboxed(self) -> None:
        """The workspace has a 學習網頁 tile that frames /site/ with a sandbox and checks message senders."""
        viewer = (STATIC / "studio-site-viewer.js").read_text(encoding="utf-8")
        for needle in ("/site/", 'sandbox="allow-scripts allow-modals allow-downloads"', "event.source"):
            self.assertIn(needle, viewer)
        self.assertIn("studio-site-viewer.js", (STATIC / "index.html").read_text(encoding="utf-8"))
        shell = (STATIC / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn("{ id: 'site', name: '學習網頁'", shell)
        panels = (STATIC / "studio-study-panels.js").read_text(encoding="utf-8")
        self.assertIn("site: { label: '學習網頁', types: ['learning_site'] }", panels)


if __name__ == "__main__":
    unittest.main()
