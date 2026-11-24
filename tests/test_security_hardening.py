"""Offline regression tests for the TASK-028 security hardening (Refs: ISSUE-045..050, ADR-013).

Covers note-pipeline path traversal, Markdown `javascript:` links, the Content-Security-Policy
header, literature PDF fallback traversal, artifact course-code traversal, empty Host headers,
and `confirm` gating on literature MCP tools.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Generator
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import CourseRecord
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.adapters.literature.legacy_import import (
    import_legacy_literature_db,
    safe_pdf_name,
)
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.literature import Reference
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import PathSafetyError, validate_path_segment
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_notes import McpNoteGenerateInput
from notebooklm_batch_studio.entrypoints.mcp_qa_notes import QANoteInput
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.converters.report_converter import markdown_fragment
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)
from notebooklm_batch_studio.services.notes.state_manager import _safe_key
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from tests.dummy_client import DummyStudioClient


class _RecordingDriver:
    """Driver stub that records uploads and never returns usable output."""

    def __init__(self) -> None:
        self.uploaded: list[Path] = []

    def open_chapter_chat(self, title: str = "") -> None:
        del title

    def set_model(self, model_name: str) -> None:
        del model_name

    def upload_files(self, paths: list[Path]) -> None:
        self.uploaded.extend(paths)

    def rename_chat(self, title: str) -> bool:
        del title
        return True

    def send_prompt_and_read(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "- [核心] {{定義:信度}} 測試內容。\n<!-- END -->"


def _cfg(root: Path) -> AppConfig:
    data_dir = root / "data"
    return AppConfig(
        app_env="test",
        log_to_file=False,
        data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
        http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
    )


class NotePathTraversalTests(unittest.TestCase):
    """Note pipeline must refuse identifiers and paths that escape the allowed roots (ISSUE-045)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = _cfg(self.root)
        self.driver = _RecordingDriver()

        @contextmanager
        def _factory(req: ChapterNoteRequest) -> Generator[_RecordingDriver, None, None]:
            del req
            yield self.driver

        self.svc = NotePipelineService(self.cfg, driver_factory=_factory)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_segment_validator(self) -> None:
        for bad in ("", ".", "..", "../x", "a/b", "a\\b", ".hidden", "x\x00y"):
            with self.assertRaises(PathSafetyError, msg=bad):
                validate_path_segment(bad, "course_key")
        self.assertEqual(validate_path_segment("PSY201", "course_key"), "PSY201")
        self.assertEqual(validate_path_segment("心理學 研究法-1", "course_key"), "心理學 研究法-1")

    def test_course_key_traversal_rejected(self) -> None:
        req = ChapterNoteRequest(course_key="../../escape", course_name="x", chapter_id="ch01")
        with self.assertRaises(PathSafetyError):
            self.svc.run_chapter(req)
        self.assertFalse((self.root / "escape").exists())

    def test_chapter_id_traversal_rejected(self) -> None:
        req = ChapterNoteRequest(course_key="PSY201", course_name="x", chapter_id="../../../pwn")
        with self.assertRaises(PathSafetyError):
            self.svc.run_chapter(req)
        with self.assertRaises(PathSafetyError):
            self.svc.read_stitched_note("PSY201", "../x")

    def test_study_dir_outside_roots_rejected(self) -> None:
        outside = self.root / "elsewhere"
        req = ChapterNoteRequest(course_key="PSY201", course_name="x", chapter_id="ch01", study_dir=outside)
        with self.assertRaises(PathSafetyError):
            self.svc.run_chapter(req)
        self.assertFalse(outside.exists())

    def test_pdf_outside_roots_or_not_pdf_rejected(self) -> None:
        secret = self.root / "secret.pdf"
        secret.write_bytes(b"%PDF-1.4")
        req = ChapterNoteRequest(course_key="PSY201", course_name="x", chapter_id="ch01", pdf_path=secret)
        with self.assertRaises(PathSafetyError):
            self.svc.run_chapter(req)
        txt = self.cfg.data_dir / "notes.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text("x", encoding="utf-8")
        req2 = ChapterNoteRequest(course_key="PSY201", course_name="x", chapter_id="ch01", pdf_path=txt)
        with self.assertRaises(PathSafetyError):
            self.svc.run_chapter(req2)
        self.assertEqual(self.driver.uploaded, [])

    def test_pdf_in_registered_source_dir_allowed(self) -> None:
        source_dir = self.root / "icloud" / "PSY201"
        source_dir.mkdir(parents=True)
        pdf = source_dir / "01.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        @contextmanager
        def _factory(req: ChapterNoteRequest) -> Generator[_RecordingDriver, None, None]:
            del req
            yield self.driver

        svc = NotePipelineService(
            self.cfg, driver_factory=_factory, source_dir_resolver=lambda _key: source_dir
        )
        req = ChapterNoteRequest(
            course_key="PSY201",
            course_name="x",
            chapter_id="ch01",
            pdf_path=pdf,
            steps_override=["04_cornell"],
        )
        svc.run_chapter(req)
        self.assertEqual(self.driver.uploaded, [pdf.resolve()])

    def test_http_generate_rejects_traversal(self) -> None:
        self.cfg.db_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(create_db_engine(self.cfg.database_url))
        app = create_app(config=self.cfg)
        app.state.note_pipeline_service = self.svc
        client = TestClient(app)
        resp = client.post(
            "/api/notes/generate",
            json={"course_key": "../../x", "course_name": "x", "chapter_id": "ch01"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_import_legacy_checks_source_dir_and_allows_whitelisted(self) -> None:
        outside = self.root / "outside_legacy"
        outside.mkdir(parents=True)
        (outside / "ch01_導論_學習筆記.md").write_text("# hi", encoding="utf-8")
        with self.assertRaises(PathSafetyError):
            self.svc.import_legacy(outside, "PSY201")
        allowed_svc = NotePipelineService(replace(self.cfg, legacy_note_studio_dir=outside))
        res = allowed_svc.import_legacy(outside, "PSY201")
        self.assertEqual(res["copied"], ["ch01_導論_學習筆記.md"])

    def test_http_notes_endpoints_return_400_on_unsafe_inputs(self) -> None:
        self.cfg.db_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(create_db_engine(self.cfg.database_url))
        app = create_app(config=self.cfg)
        app.state.note_pipeline_service = self.svc
        client = TestClient(app)
        bad_gets = (
            "/api/notes/content/.hidden/ch01",
            "/api/notes/content/PSY201/.hidden",
            "/api/notes/chapters/.hidden",
            "/api/notes/status/.hidden",
        )
        for url in bad_gets:
            self.assertEqual(client.get(url).status_code, 400, msg=url)
        for url in ("/api/notes/pause/.hidden", "/api/notes/resume/.hidden"):
            self.assertEqual(client.post(url).status_code, 400, msg=url)
        outside = self.root / "outside_notes"
        self.assertEqual(
            client.post(
                "/api/notes/import_legacy", json={"source_dir": str(outside), "course_key": "PSY201"}
            ).status_code,
            400,
        )
        self.assertEqual(
            client.post(
                "/api/notes/import_legacy",
                json={"source_dir": str(self.cfg.data_dir), "course_key": ".hidden"},
            ).status_code,
            400,
        )

    def test_state_manager_safe_key_and_mcp_error_payload(self) -> None:
        self.assertEqual(_safe_key(".."), "default")
        self.assertEqual(_safe_key(".hidden"), "hidden")
        self.assertEqual(_safe_key("PSY 201/x"), "PSY_201_x")
        self.cfg.db_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(create_db_engine(self.cfg.database_url))
        mcp = build_mcp_server(config=self.cfg)
        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        self.assertIn("error", json.loads(tools["notes_read_chapter"].fn(".hidden", "ch01")))
        self.assertIn("error", json.loads(tools["notes_get_status"].fn(".hidden")))


class XssAndHeaderTests(unittest.TestCase):
    """Rendered Markdown and HTTP responses must not enable script execution (ISSUE-046)."""

    def test_markdown_drops_dangerous_link_schemes(self) -> None:
        html = markdown_fragment(
            "[a](javascript:alert(1)) [b](JaVaScRiPt:x) ![c](data:text/html,x) [d](vbscript:x) "
            "[ok](https://example.org/p) [rel](#sec)"
        )
        lowered = html.lower()
        self.assertNotIn("javascript:", lowered)
        self.assertNotIn("vbscript:", lowered)
        self.assertNotIn("data:text/html", lowered)
        self.assertIn('href="https://example.org/p"', html)
        self.assertIn('href="#sec"', html)

    def test_csp_and_empty_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(create_db_engine(cfg.database_url))
            client = TestClient(create_app(config=cfg))
            resp = client.get("/")
            csp = resp.headers.get("content-security-policy", "")
            self.assertIn("script-src 'self'", csp)
            self.assertIn("object-src 'none'", csp)
            self.assertIn("frame-ancestors 'self'", csp)
            self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")
            empty = client.get("/api/courses", headers={"host": ""})
            self.assertEqual(empty.status_code, 400)

    def test_artifact_download_rejects_parent_course_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(create_db_engine(cfg.database_url))
            other = cfg.courses_output_dir / "OTHER"
            other.mkdir(parents=True)
            (other / "secret.md").write_text("secret", encoding="utf-8")
            client = TestClient(create_app(config=cfg))
            resp = client.get("/api/artifacts/%2E%2E/download/OTHER/secret.md")
            self.assertIn(resp.status_code, (400, 403, 404))
            self.assertNotIn("secret", resp.text)

    def test_static_js_escaping_and_safe_url_guards(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "src/notebooklm_batch_studio/entrypoints/static"
        escape_js = (static_dir / "studio-escape.js").read_text(encoding="utf-8")
        self.assertIn("&quot;", escape_js)
        self.assertIn("&#39;", escape_js)
        self.assertIn("function safeHttpUrl", escape_js)
        for name in ("studio-study-panels.js", "studio.js"):
            self.assertNotIn("explainMistake('${", (static_dir / name).read_text(encoding="utf-8"), msg=name)
        lit_actions = (static_dir / "studio-literature-actions.js").read_text(encoding="utf-8")
        self.assertIn("safeHttpUrl(nbData.notebook_url)", lit_actions)
        lit_ui = (static_dir / "studio-literature-ui.js").read_text(encoding="utf-8")
        self.assertIn("window.escHtml", lit_ui)
        self.assertIn("&#39;", lit_ui)


class ArtifactStudyDirTests(unittest.TestCase):
    """Artifact view/download must find outputs of courses migrated to a study folder (ISSUE-050)."""

    def test_view_and_download_use_study_dir_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            study_dir = cfg.study_root_dir / "115-1" / "生涯諮商"
            out_dir = study_dir / "03 Notes" / "NotebookLM" / "03_Topic"
            out_dir.mkdir(parents=True)
            (out_dir / "study_guide.md").write_text("# 指南\n內容", encoding="utf-8")
            with make_session_factory(engine)() as session:
                session.add(
                    CourseRecord(
                        code="115-1", name="生涯諮商", source_dir=str(study_dir), study_dir=str(study_dir)
                    )
                )
                session.commit()
            client = TestClient(create_app(config=cfg))
            view = client.get("/api/artifacts/115-1/view/03_Topic/study_guide.md")
            self.assertEqual(view.status_code, 200, view.text)
            self.assertIn("指南", view.text)
            download = client.get("/api/artifacts/115-1/download/03_Topic/study_guide.md")
            self.assertEqual(download.status_code, 200)
            escape = client.get("/api/artifacts/115-1/download/../../../../secret.md")
            self.assertIn(escape.status_code, (403, 404))


class LiteratureHardeningTests(unittest.TestCase):
    """Literature PDF lookup and MCP tools must stay inside their guard rails (ISSUE-047, ISSUE-048)."""

    def test_pdf_fallback_does_not_escape_literature_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            (cfg.data_dir / "outside.pdf").write_bytes(b"%PDF-1.4")
            cfg.literature_dir.mkdir(parents=True, exist_ok=True)
            with make_session_factory(engine)() as session:
                repo = LiteratureRepository(session)
                mgr = LiteratureManager(
                    cfg, repo, CourseRepository(session), runtime=AdapterLiteratureRuntime(cfg)
                )
                repo.upsert_item(
                    TrackedItem(
                        key="evil",
                        input="x",
                        reference=Reference(key="evil", citation="x"),
                        apa="x",
                        status=ItemStatus.DOWNLOADED,
                        file="../outside.pdf",
                    )
                )
                self.assertIsNone(mgr.resolve_pdf_path("evil"))

    def test_legacy_import_drops_traversing_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            legacy_pdf_dir = root / "legacy" / "pdfs"
            legacy_pdf_dir.mkdir(parents=True)
            (legacy_pdf_dir / "ok.pdf").write_bytes(b"%PDF-1.4")
            (root / "legacy" / "secret.pdf").write_bytes(b"%PDF-1.4 secret")
            legacy_db = root / "legacy" / "literature.db"
            cols = (
                "key,input,has_reference,kind,pdf_urls,citation,apa,doi,arxiv_id,title,author,"
                "status,file,note,source,check_note,position"
            )
            conn = sqlite3.connect(legacy_db)
            conn.execute(f"CREATE TABLE items ({cols})")
            for pos, (key, file_name) in enumerate((("good", "ok.pdf"), ("evil", "../secret.pdf"))):
                conn.execute(
                    f"INSERT INTO items ({cols}) "
                    "VALUES (?,?,0,'','','','','','','','','downloaded',?,'','','',?)",
                    (key, key, file_name, pos),
                )
            conn.commit()
            conn.close()
            with make_session_factory(engine)() as session:
                repo = LiteratureRepository(session)
                res = import_legacy_literature_db(legacy_db, legacy_pdf_dir, repo, cfg.literature_dir)
                self.assertEqual(res, {"imported": 2, "skipped": 0, "copied_pdfs": 1})
                evil = repo.get_item("evil")
                assert evil is not None
                self.assertEqual(evil.file, "")
                self.assertFalse((cfg.literature_dir.parent / "secret.pdf").exists())
        self.assertEqual(safe_pdf_name("a/b.pdf"), "")
        self.assertEqual(safe_pdf_name("paper.PDF"), "paper.PDF")

    def test_mutating_literature_tools_require_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(create_db_engine(cfg.database_url))
            app = create_app(config=cfg)
            mcp = build_mcp_server(
                service=app.state.service,
                study_service=app.state.study_service,
                config=cfg,
                literature_jobs=app.state.literature_jobs,
                preferences=app.state.preferences,
                qa_notes=app.state.qa_notes,
            )
            tools = {t.name: t for t in mcp._tool_manager.list_tools()}
            calls: dict[str, dict[str, Any]] = {
                "add_literature": {"text": "10.1000/x"},
                "process_literature": {},
                "refresh_literature": {"key": "x"},
                "import_literature_to_course": {"key": "x"},
                "unarchive_literature": {"key": "x"},
                "sync_literature_notebook": {},
                "generate_literature_review": {"key": "x"},
                "save_qa_note": {"code": "X", "note": QANoteInput(title="t", content_markdown="a")},
                "notes_generate_chapter": {
                    "params": McpNoteGenerateInput(course_key="X", course_name="x", chapter_id="ch01")
                },
                "notes_pause_course": {"course_key": "X"},
                "notes_push_to_source": {"course_key": "X", "chapter_id": "ch01", "notebook_id": "nb-1"},
                "notes_import_legacy": {"source_dir": str(cfg.data_dir), "course_key": "X"},
            }
            for name, kwargs in calls.items():
                result = tools[name].fn(**kwargs)
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                payload = json.loads(result)
                self.assertFalse(payload["confirmed"], msg=name)
                self.assertIn("confirm", str(payload.get("warning", "")).lower(), msg=name)


class CourseSourcePathTests(unittest.TestCase):
    """Course custom-source uploads must stay inside DATA_DIR, STUDY_ROOT_DIR, or the course folder."""

    def test_upload_custom_source_rejects_outside_pdf_and_allows_course_source_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            cfg.db_dir.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            course_dir = root / "icloud" / "BIO101"
            course_dir.mkdir(parents=True)
            allowed_pdf = course_dir / "01.pdf"
            allowed_pdf.write_bytes(b"%PDF-1.4 ok")
            outside_pdf = root / "sibling_user_file.pdf"
            outside_pdf.write_bytes(b"%PDF-1.4 outside")
            with make_session_factory(engine)() as session:
                course_repo = CourseRepository(session)
                course_repo.save_course(Course(code="BIO101", name="Bio", source_dir=str(course_dir)))
                svc = BatchStudioService(course_repo, QueueRepository(session), DummyStudioClient(), cfg)
                client = TestClient(create_app(config=cfg, service=svc, study_service=mock.MagicMock()))
                bad = client.post("/api/courses/BIO101/sources", json={"file_path": str(outside_pdf)})
                self.assertEqual(bad.status_code, 422)
                ok = client.post("/api/courses/BIO101/sources", json={"file_path": str(allowed_pdf)})
                self.assertEqual(ok.status_code, 200)


if __name__ == "__main__":
    unittest.main()
