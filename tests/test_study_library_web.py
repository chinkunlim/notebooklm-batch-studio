"""SPEC-016: web entry points for study-library registration, scratch filing, and course display names."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.models import ArtifactJobRecord, CourseRecord
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, CourseStatus, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"


def _library_js() -> str:
    """Return the study-library web script source.

    Returns:
        Contents of `studio-library.js` (empty string when missing).
    """
    path = STATIC / "studio-library.js"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class StudyLibraryWebTests(unittest.TestCase):
    """Scenarios 16a–16d: register, register-folder, filing, and display-name entry points."""

    def setUp(self) -> None:
        """Create an isolated DATA_DIR with one registered, one unregistered and one non-standard folder."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name) / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

        self.c1_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        (self.c1_dir / "02 Handouts").mkdir(parents=True)
        (self.c1_dir / "02 Handouts" / "01_ch1.pdf").write_bytes(b"%PDF")
        self.past_dir = self.cfg.study_root_dir / "113-1" / "CP__30000-團體諮商"
        (self.past_dir / "02 Handouts").mkdir(parents=True)
        (self.past_dir / "02 Handouts" / "01_intro.pdf").write_bytes(b"%PDF")
        self.misc_dir = self.cfg.study_root_dir / "113-1" / "專題"
        (self.misc_dir / "02 Handouts").mkdir(parents=True)
        self.scratch_file = self.cfg.scratch_kind_dir("uploads") / "a.pdf"
        self.scratch_file.parent.mkdir(parents=True, exist_ok=True)
        self.scratch_file.write_bytes(b"%PDF")

        with self.session_factory() as session:
            CourseRepository(session).save_course(
                Course(
                    code="115-1_CP31000",
                    name="生涯諮商",
                    source_dir=str(self.c1_dir),
                    study_dir=str(self.c1_dir),
                    term="115-1",
                    subject="生涯諮商與實務",
                    course_no="CP31000",
                    status=CourseStatus.ACTIVE,
                    lectures=[Lecture(no=1, topic="Ch1", filename="01_ch1.pdf", sha256="abc")],
                )
            )
            session.commit()
        self.client = TestClient(create_app(config=self.cfg))
        self.tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]

    def tearDown(self) -> None:
        """Dispose the engine and remove the temporary directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_web_ui_wires_register_and_register_folder(self) -> None:
        """Scenarios 16a/16b: the record page script calls register and register-folder and is loaded."""
        js = _library_js()
        self.assertIn("/api/study/library/register", js)
        self.assertIn("/api/study/library/register-folder", js)
        self.assertIn("登錄本學期所有未登錄課程", js)
        self.assertIn("手動登錄", js)
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("studio-library.js", html)

    def test_register_from_record_view_creates_record_only_course(self) -> None:
        """Scenario 16a/16b: unregistered and non-standard folders register record-only without jobs."""
        rec = self.client.get("/api/study/record").json()
        past = next(t for t in rec["terms"] if t["term"] == "113-1")
        cand = next(c for c in past["courses"] if c["status"] == "unregistered")
        self.assertIn("專題", past["others"])
        res = self.client.post("/api/study/library/register", json={"codes": [cand["code"]], "archive": True})
        self.assertEqual(res.status_code, 200, res.text)
        res2 = self.client.post(
            "/api/study/library/register-folder",
            json={"term": "113-1", "folder": "專題", "course_no": "CP39000"},
        )
        self.assertEqual(res2.status_code, 200, res2.text)
        with self.session_factory() as session:
            row = session.get(CourseRecord, cand["code"])
            assert row is not None
            self.assertEqual((row.profile, row.status), ("record-only", "archived"))
            self.assertIsNotNone(session.get(CourseRecord, "113-1_CP39000"))
            self.assertEqual(session.query(ArtifactJobRecord).count(), 0)

    def test_record_view_exposes_study_dir_and_web_wires_filing(self) -> None:
        """Scenario 16c: filing and unfiling round-trip, record exposes study_dir, script wires both."""
        rec = self.client.get("/api/study/record").json()
        cur = next(c for t in rec["terms"] for c in t["courses"] if c["code"] == "115-1_CP31000")
        self.assertEqual(cur["study_dir"], str(self.c1_dir))
        items = self.client.get("/api/study/unfiled").json()["items"]
        self.assertEqual([i["name"] for i in items], ["a.pdf"])
        filed = self.client.post(
            "/api/study/file",
            json={"path": str(self.scratch_file), "course_code": "115-1_CP31000", "role": "materials"},
        )
        self.assertEqual(filed.status_code, 200, filed.text)
        dest = Path(filed.json()["dest"])
        self.assertEqual(dest.parent.name, "01 Materials")
        back = self.client.post("/api/study/unfile", json={"path": str(dest)})
        self.assertEqual(back.status_code, 200, back.text)
        self.assertEqual(Path(back.json()["dest"]).parent.name, "115-1_CP31000")
        js = _library_js()
        for needle in ("/api/study/unfiled", "/api/study/file", "/api/study/unfile", "撤銷歸檔"):
            self.assertIn(needle, js)

    def test_set_display_name_http_mcp_and_web(self) -> None:
        """Scenario 16d: display name changes via HTTP and MCP; code, subject and folder stay put."""
        res = self.client.put("/api/courses/115-1_CP31000/name", json={"name": "  生涯諮商與實務  "})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json(), {"code": "115-1_CP31000", "name": "生涯諮商與實務"})
        names = {c["code"]: c["name"] for c in self.client.get("/api/courses").json()}
        self.assertEqual(names["115-1_CP31000"], "生涯諮商與實務")
        self.assertEqual(self.client.put("/api/courses/NOPE/name", json={"name": "x"}).status_code, 404)
        blank = self.client.put("/api/courses/115-1_CP31000/name", json={"name": "  "})
        self.assertEqual(blank.status_code, 422)

        tool = self.tools["set_course_display_name"].fn
        refused = json.loads(tool("115-1_CP31000", "別的名字"))
        self.assertFalse(refused["confirmed"])
        done = json.loads(tool("115-1_CP31000", "生涯諮商", confirm=True))
        self.assertEqual(done["name"], "生涯諮商")
        with self.session_factory() as session:
            row = session.get(CourseRecord, "115-1_CP31000")
            assert row is not None
            expected = ("生涯諮商", "生涯諮商與實務", str(self.c1_dir))
            self.assertEqual((row.name, row.subject, row.study_dir), expected)
        self.assertIn("修改課程名稱", (STATIC / "studio-batch.js").read_text(encoding="utf-8"))
        self.assertIn("/name", _library_js())


if __name__ == "__main__":
    unittest.main()
