"""Tests for Task 13 HTTP, MCP, and Web study library / lifecycle / learning record entrypoints."""

from __future__ import annotations

import asyncio
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints
from unittest import mock

from fastapi.testclient import TestClient
from pydantic import BaseModel

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, CourseStatus, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService


def _dummy_arg_for_param(param: inspect.Parameter, resolved_ann: Any = None) -> Any:
    """Synthesize a safe dummy argument matching a parameter's type annotation for confirm=False scans."""
    if param.name == "confirm":
        return False
    ann = resolved_ann if resolved_ann is not None else param.annotation
    origin = get_origin(ann)
    args = get_args(ann)
    if origin is not None and type(None) in args and param.default is None:
        return None
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        fields: dict[str, Any] = {}
        for fname, finfo in ann.model_fields.items():
            if not finfo.is_required():
                continue
            fann = finfo.annotation
            if fann is int or "int" in str(fann):
                fields[fname] = 1
            elif fann is bool or "bool" in str(fann):
                fields[fname] = False
            elif get_origin(fann) in (list, tuple, set) or "list[" in str(fann):
                fields[fname] = ["dummy"]
            else:
                fields[fname] = "quiz_1" if fname == "kind" else "dummy"
        return ann(**fields)
    if origin in (list, tuple, set) or "list[" in str(ann):
        return ["dummy"]
    if origin is dict or "dict[" in str(ann):
        return {}
    if ann is int or ann == "int" or "int" in str(ann):
        return 1
    if ann is bool or ann == "bool":
        return False
    if "course_no" in param.name:
        return "CP30000"
    if "term" in param.name:
        return "115-1"
    if "role" in param.name or "category" in param.name:
        return "materials"
    return "dummy"


class StudyLibraryApiAndMcpTests(unittest.TestCase):
    """BDD Scenario 13: HTTP routes, MCP tools, error statuses, and global MCP confirm guard."""

    def setUp(self) -> None:
        """Create an isolated temporary DATA_DIR, database, and seeded study library."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

        # Seed study folders: 1 registered active course, 1 unregistered candidate, 1 non-standard folder.
        self.c1_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        (self.c1_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (self.c1_dir / "02 Handouts" / "01_ch1.pdf").write_bytes(b"%PDF")
        (self.c1_dir / "05 Assignments").mkdir(parents=True, exist_ok=True)

        self.c2_dir = self.cfg.study_root_dir / "114-2" / "CP__20100-發展心理學"
        (self.c2_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (self.c2_dir / "02 Handouts" / "01_dev.pdf").write_bytes(b"%PDF")

        self.misc_dir = self.cfg.study_root_dir / "115-1" / "研究專題"
        (self.misc_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (self.misc_dir / "02 Handouts" / "intro.pdf").write_bytes(b"%PDF")

        self.scratch_file = self.cfg.scratch_kind_dir("literature") / "paper.pdf"
        self.scratch_file.parent.mkdir(parents=True, exist_ok=True)
        self.scratch_file.write_bytes(b"%PDF")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(self.c1_dir),
                    study_dir=str(self.c1_dir),
                    term="115-1",
                    course_no="CP30000",
                    status=CourseStatus.ACTIVE,
                    lectures=[Lecture(no=1, topic="Ch1", filename="01_ch1.pdf", sha256="abc")],
                )
            )
            session.commit()

        self.client = TestClient(create_app(config=self.cfg))
        self.mcp = build_mcp_server(config=self.cfg)
        self.tools = self.mcp._tool_manager._tools  # type: ignore[attr-defined]

    def tearDown(self) -> None:
        """Dispose database engine and clean temporary directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_http_routes_cover_layout_library_filing_lifecycle_and_record(self) -> None:
        """All 12 Task 13 HTTP endpoints work, courses list includes metadata, and bad codes fail 400/404."""
        # 1. Courses summary includes term, course_no, status
        courses_resp = self.client.get("/api/courses")
        self.assertEqual(courses_resp.status_code, 200)
        row = courses_resp.json()[0]
        self.assertEqual(row["term"], "115-1")
        self.assertEqual(row["course_no"], "CP30000")
        self.assertEqual(row["status"], "active")

        # 2. Study layout & library scan
        layout_resp = self.client.get("/api/study/layout")
        self.assertEqual(layout_resp.status_code, 200)
        self.assertEqual(layout_resp.json()["names"]["materials"], "01 Materials")

        lib_resp = self.client.get("/api/study/library")
        self.assertEqual(lib_resp.status_code, 200)
        terms = {t["term"]: t for t in lib_resp.json()["terms"]}
        self.assertIn("114-2", terms)
        self.assertIn("研究專題", terms["115-1"]["others"])

        # 3. Register past courses & non-standard folder
        reg_resp = self.client.post(
            "/api/study/library/register", json={"codes": ["114-2_CP20100"], "archive": True}
        )
        self.assertEqual(reg_resp.status_code, 200)
        self.assertEqual(reg_resp.json()["results"][0]["status"], "archived")

        reg_folder = self.client.post(
            "/api/study/library/register-folder",
            json={"term": "115-1", "folder": "研究專題", "course_no": "PROJ115"},
        )
        self.assertEqual(reg_folder.status_code, 200)
        self.assertEqual(reg_folder.json()["code"], "115-1_PROJ115")
        self.assertEqual(
            self.client.post(
                "/api/study/library/register-folder",
                json={"term": "115-1", "folder": "no-such-folder", "course_no": "X1"},
            ).status_code,
            404,
        )

        # 4. List unfiled, file, unfile
        unfiled = self.client.get("/api/study/unfiled", params={"kind": "literature"})
        self.assertEqual(unfiled.status_code, 200)
        self.assertEqual(len(unfiled.json()["items"]), 1)

        filed = self.client.post(
            "/api/study/file",
            json={
                "path": str(self.scratch_file),
                "course_code": "115-1_CP30000",
                "role": "materials",
                "subfolder": "Papers",
            },
        )
        self.assertEqual(filed.status_code, 200)
        dest_path = filed.json()["dest"]
        self.assertTrue(Path(dest_path).is_file())

        unfiled_back = self.client.post("/api/study/unfile", json={"path": dest_path})
        self.assertEqual(unfiled_back.status_code, 200)
        self.assertTrue(Path(unfiled_back.json()["dest"]).is_file())

        # 5. Archive, restore, rename (default dry_run=True then dry_run=False)
        self.assertEqual(self.client.post("/api/courses/115-1_CP30000/archive").status_code, 200)
        self.assertEqual(self.client.post("/api/courses/115-1_CP30000/restore").status_code, 200)
        self.assertEqual(self.client.post("/api/courses/NO_SUCH/archive").status_code, 404)

        dry = self.client.post("/api/courses/115-1_CP30000/rename", json={"new_code": "115-1_CP30001"})
        self.assertEqual(dry.status_code, 200)
        self.assertTrue(dry.json()["dry_run"])

        self.assertEqual(
            self.client.post("/api/courses/115-1_CP30000/rename", json={"new_code": "../bad"}).status_code,
            400,
        )
        applied = self.client.post(
            "/api/courses/115-1_CP30000/rename", json={"new_code": "115-1_CP30001", "dry_run": False}
        )
        self.assertEqual(applied.status_code, 200)
        self.assertFalse(applied.json()["dry_run"])

        # 6. Learning record & MD/PDF export
        rec = self.client.get("/api/study/record")
        self.assertEqual(rec.status_code, 200)
        self.assertTrue(len(rec.json()["terms"]) >= 1)

        md_exp = self.client.get("/api/study/record/export", params={"format": "md"})
        self.assertEqual(md_exp.status_code, 200)
        self.assertIn("# 學習紀錄", md_exp.text)

        pdf_exp = self.client.get("/api/study/record/export", params={"format": "pdf"})
        self.assertEqual(pdf_exp.status_code, 200)
        self.assertTrue(pdf_exp.content.startswith(b"%PDF"))

    def test_mcp_study_library_tools_and_confirm_guards(self) -> None:
        """All 11 MCP tools in mcp_study_library exist, pass happy paths, and rename defaults dry_run."""
        expected = {
            "get_study_layout",
            "scan_study_library",
            "register_past_courses",
            "register_study_folder",
            "list_unfiled",
            "file_item",
            "unfile_item",
            "set_course_archived",
            "rename_course_code",
            "get_learning_record",
            "export_learning_record",
        }
        self.assertTrue(expected <= set(self.tools.keys()))

        layout = json.loads(self.tools["get_study_layout"].fn())
        self.assertIn("materials", layout["names"])
        lib = json.loads(self.tools["scan_study_library"].fn())
        self.assertTrue(len(lib["terms"]) >= 1)
        self.assertEqual(len(json.loads(self.tools["list_unfiled"].fn())["items"]), 1)

        dry = json.loads(self.tools["rename_course_code"].fn("115-1_CP30000", "115-1_CP30001", confirm=True))
        self.assertTrue(dry["dry_run"])
        applied = json.loads(
            self.tools["rename_course_code"].fn("115-1_CP30000", "115-1_CP30001", dry_run=False, confirm=True)
        )
        self.assertFalse(applied["dry_run"])

        arch = json.loads(self.tools["set_course_archived"].fn("115-1_CP30001", True, confirm=True))
        self.assertEqual(arch["status"], "archived")
        rec = json.loads(self.tools["get_learning_record"].fn())
        self.assertIn("terms", rec)
        md = json.loads(self.tools["export_learning_record"].fn(format="md"))
        self.assertIn("# 學習紀錄", md["markdown"])

    def test_all_mcp_tools_with_confirm_parameter_require_confirmation(self) -> None:
        """Every registered MCP tool exposing `confirm` refuses with `confirmed: false` when confirm=False."""
        checked: list[str] = []
        with (
            mock.patch.object(
                BatchStudioService, "preview_course_folders", new=mock.AsyncMock(return_value=[])
            ),
        ):
            for name, tool in sorted(self.tools.items()):
                sig = inspect.signature(tool.fn)
                if "confirm" not in sig.parameters:
                    continue
                try:
                    hints = get_type_hints(tool.fn)
                except Exception:
                    hints = {}
                kwargs = {
                    pname: _dummy_arg_for_param(param, hints.get(pname))
                    for pname, param in sig.parameters.items()
                }
                raw = tool.fn(**kwargs)
                if inspect.isawaitable(raw):
                    raw = asyncio.run(raw)
                payload = json.loads(raw)
                self.assertIn("confirmed", payload, f"{name} missing confirmed key: {payload}")
                self.assertIs(
                    payload["confirmed"], False, f"{name} did not refuse when confirm=False: {payload}"
                )
                checked.append(name)
        self.assertGreaterEqual(len(checked), 20)


if __name__ == "__main__":
    unittest.main()
