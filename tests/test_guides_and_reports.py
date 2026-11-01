"""Tests: saved artifact selections, concept-explanation reports, rendered report HTML, usage guide."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.domain.naming import NAMING_BY_TYPE
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner
from notebooklm_batch_studio.services.converters.report_converter import report_to_html
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.worker_pool import generate_jobs_for_course
from tests.test_notebooklm_generation import RecordingProtocolClient


def make_course(tmp: Path, chapter: list[str] | None = None, whole: list[str] | None = None) -> Course:
    """Build a one-lecture course, optionally with a custom artifact selection.

    Args:
        tmp: Source folder.
        chapter: Selected per-lecture artifact types.
        whole: Selected course-wide artifact types.

    Returns:
        Course entity.
    """
    return Course(
        code="BIO101",
        name="細胞生物學",
        source_dir=str(tmp),
        notebook_id="nb",
        lectures=[Lecture(no=1, topic="細胞膜", filename="01_ch_a.pdf", sha256="a", source_id="s1")],
        selected_chapter_artifacts=chapter or [],
        selected_course_artifacts=whole or [],
    )


class SelectionPersistenceTest(unittest.TestCase):
    """A custom selection made in the web app survives a rescan."""

    def test_selection_is_kept_when_rescan_has_none(self) -> None:
        """Saving with a selection, then rescanning without one, still generates the selection."""
        with tempfile.TemporaryDirectory() as tmp_name:
            engine = create_db_engine("sqlite://")
            Base.metadata.create_all(engine)
            with session_scope(engine) as s:
                repo = CourseRepository(s)
                repo.save_course(make_course(Path(tmp_name), ["infographic", "quiz_1"], ["course_mock_exam"]))
                repo.save_course(make_course(Path(tmp_name)))  # watcher / batch rescan
                course = repo.get_course("BIO101")
                assert course is not None
                self.assertEqual(course.selected_chapter_artifacts, ["infographic", "quiz_1"])
                types = sorted(j.artifact_type.value for j in generate_jobs_for_course(course))
                self.assertEqual(types, ["course_mock_exam", "infographic", "quiz_1"])


class ReportTest(unittest.IsolatedAsyncioTestCase):
    """Concept-explanation reports and their HTML page."""

    def test_report_html_renders_markdown_and_escapes_html(self) -> None:
        """Headings, tables and bold become HTML; raw tags from the source are escaped."""
        page = report_to_html(
            "T<1>", "# 標題\n\n**重點**\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<script>x</script>"
        )
        self.assertIn("<h1>標題</h1>", page)
        self.assertIn("<strong>重點</strong>", page)
        self.assertIn("<table>", page)
        self.assertNotIn("<script>", page)
        self.assertIn("<title>T&lt;1&gt;</title>", page)

    async def test_concept_report_uses_concept_format(self) -> None:
        """REPORTS_CONCEPT asks NotebookLM for concept_explanation and writes a rendered page."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            out = tmp / "out"
            out.mkdir()
            client = RecordingProtocolClient()
            cfg = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
            runner = ArtifactRunner(client, cfg)  # type: ignore[arg-type]
            job = ArtifactJob(
                id="r", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.REPORTS_CONCEPT
            )
            path = await runner.process_job(job, make_course(tmp), "nb", ["s1"], out)
            self.assertEqual(client.called("generate_report")[0]["report_format"], "concept_explanation")
            self.assertTrue(path.endswith("BIO101_L1_concept_explanation.md"))
            self.assertTrue((out / "BIO101_L1_concept_explanation_interactive.html").exists())
            self.assertIn("reports_concept_explanation", NAMING_BY_TYPE)


class UsageGuideTest(unittest.TestCase):
    """The usage guide is served over HTTP and MCP."""

    def test_http_and_mcp(self) -> None:
        """GET /api/usage-guide and MCP get_usage_guide return the same sections."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            cfg = AppConfig(
                data_dir=tmp / "data",
                notebooklm_home=tmp / "cfg",
                log_to_file=False,
                http_allowed_hosts=("testserver",),
            )
            engine = create_db_engine("sqlite://")
            Base.metadata.create_all(engine)
            with session_scope(engine) as s:
                service = BatchStudioService(CourseRepository(s), QueueRepository(s), mock.MagicMock(), cfg)
                http = TestClient(create_app(config=cfg, service=service, study_service=mock.MagicMock()))
                sections = http.get("/api/usage-guide").json()["sections"]
                self.assertGreaterEqual(len(sections), 4)
                mcp = build_mcp_server(service=service, study_service=mock.MagicMock(), config=cfg)
                tool = mcp._tool_manager._tools["get_usage_guide"].fn  # type: ignore[attr-defined]
                self.assertEqual(json.loads(tool())["sections"], sections)


if __name__ == "__main__":
    unittest.main()
