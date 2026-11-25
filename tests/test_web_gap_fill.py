"""SPEC-019: web entry points for course output mode, note-generation resume, and Gemini cookie retention."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.entrypoints.api import create_app

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CODE = "115-1_CP30210"


def _static(name: str) -> str:
    """Read a static web file.

    Args:
        name: File name under `entrypoints/static`.

    Returns:
        File contents.
    """
    return (STATIC / name).read_text(encoding="utf-8")


class WebGapFillTest(unittest.TestCase):
    """Scenarios 19a–19c."""

    def setUp(self) -> None:
        """Create DATA_DIR, database, a record-only course, and the web app."""
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
        course_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        course_dir.mkdir(parents=True)
        with make_session_factory(self.engine)() as session:
            CourseRepository(session).save_course(
                Course(
                    code=CODE,
                    name="心理學研究法",
                    source_dir=str(course_dir),
                    study_dir=str(course_dir),
                    profile=ProfileName.RECORD_ONLY,
                    lectures=[Lecture(no=1, topic="Intro", filename="Ch01.pdf", sha256="a")],
                )
            )
            session.commit()
        self.client = TestClient(create_app(config=self.cfg))

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_profile_switch_http_and_web(self) -> None:
        """Invalid mode is 422; record-only -> full queues jobs; the course menu wires the flow."""
        bad = self.client.post(f"/api/courses/{CODE}/profile", json={"profile": "nonsense"})
        self.assertEqual(bad.status_code, 422, bad.text)
        res = self.client.post(f"/api/courses/{CODE}/profile", json={"profile": "full"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertGreater(res.json()["new_jobs_enqueued"], 0)
        self.assertIn("openCourseProfileFlow", _static("studio-batch.js"))
        js = _static("studio-library.js")
        self.assertIn("/profile", js)
        self.assertIn("只記錄、不產生", js)

    def test_note_resume_http_and_web(self) -> None:
        """Pause then resume clears the pause flag; the notes page has a resume button."""
        self.client.post(f"/api/notes/pause/{CODE}")
        self.assertTrue(self.client.get(f"/api/notes/status/{CODE}").json()["paused"])
        res = self.client.post(f"/api/notes/resume/{CODE}")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(self.client.get(f"/api/notes/status/{CODE}").json()["paused"])
        self.assertIn("resumeNoteGeneration()", _static("index.html"))
        self.assertIn("/api/notes/resume/", _static("studio-notes-gen.js"))

    def test_gemini_retention_http_and_web(self) -> None:
        """Retention is saved with confirm, read back from auth-status, and range-checked."""
        res = self.client.post("/api/notes/gemini/retention", json={"retention_days": 60, "confirm": True})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.client.get("/api/notes/gemini/auth-status").json()["retention_days"], 60)
        too_big = self.client.post(
            "/api/notes/gemini/retention", json={"retention_days": 4000, "confirm": True}
        )
        self.assertEqual(too_big.status_code, 422)
        self.assertIn('id="ngRetentionDays"', _static("index.html"))
        js = _static("studio-notes-gen.js")
        self.assertIn("/api/notes/gemini/retention", js)
        self.assertIn("confirm: true", js)


if __name__ == "__main__":
    unittest.main()
