"""SPEC-017: NoteStudio extra files, course-complete notification, versioned adoption, backup pruning."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, ProfileName
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.adopt_outputs import AdoptOutputsService
from notebooklm_batch_studio.services.completion_notice import course_complete_hook
from notebooklm_batch_studio.services.worker_pool import WorkerPool

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CODE = "115-1_CP31000"


class _Base(unittest.TestCase):
    """Isolated DATA_DIR + DB with one registered course."""

    def setUp(self) -> None:
        """Create the temporary data directory, database and course."""
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
        self.study_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        (self.study_dir / "02 Handouts").mkdir(parents=True)
        with self.session_factory() as session:
            CourseRepository(session).save_course(
                Course(
                    code=CODE,
                    name="生涯諮商與實務",
                    source_dir=str(self.study_dir),
                    study_dir=str(self.study_dir),
                    profile=ProfileName.RECORD_ONLY,
                )
            )
            session.commit()

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()


class NoteFilesTest(_Base):
    """Scenario 17a."""

    def test_note_files_list_read_http_mcp_and_web(self) -> None:
        """Overview, PDFs and draft modules are listed; versions/layout excluded; traversal refused."""
        ns = self.study_dir / "03 Notes" / "NoteStudio"
        files = {
            "00_總覽與跨章整合筆記.md": "# 總覽",
            "學習筆記/原稿/Ch01_導論_學習筆記.md": "# Ch01",
            "學習筆記/PDF/Ch01_導論_學習筆記.pdf": "%PDF",
            "學習筆記/PDF/layout/page.pdf": "%PDF",
            "章節/ch01/目前/目前 01.md": "draft",
            "章節/ch01/版本/v1.md": "old",
        }
        for rel, body in files.items():
            (ns / rel).parent.mkdir(parents=True, exist_ok=True)
            (ns / rel).write_text(body, encoding="utf-8")
        client = TestClient(create_app(config=self.cfg))
        res = client.get(f"/api/notes/files/{CODE}")
        self.assertEqual(res.status_code, 200, res.text)
        listed = {f["relative_path"]: f for f in res.json()["files"]}
        self.assertEqual(
            set(listed),
            {
                "00_總覽與跨章整合筆記.md",
                "學習筆記/原稿/Ch01_導論_學習筆記.md",
                "學習筆記/PDF/Ch01_導論_學習筆記.pdf",
                "章節/ch01/目前/目前 01.md",
            },
        )
        self.assertTrue(listed["學習筆記/原稿/Ch01_導論_學習筆記.md"]["is_chapter"])
        self.assertEqual(listed["學習筆記/PDF/Ch01_導論_學習筆記.pdf"]["kind"], "pdf")
        md = client.get(f"/api/notes/file/{CODE}", params={"path": "00_總覽與跨章整合筆記.md"})
        self.assertEqual(md.json()["content"], "# 總覽")
        pdf = client.get(f"/api/notes/file/{CODE}", params={"path": "學習筆記/PDF/Ch01_導論_學習筆記.pdf"})
        self.assertEqual((pdf.status_code, pdf.content), (200, b"%PDF"))
        self.assertEqual(
            client.get(f"/api/notes/file/{CODE}", params={"path": "../../x.md"}).status_code, 400
        )

        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(len(json.loads(tools["notes_list_files"].fn(CODE))["files"]), 4)
        self.assertEqual(
            json.loads(tools["notes_read_file"].fn(CODE, "章節/ch01/目前/目前 01.md"))["content"], "draft"
        )
        js = (STATIC / "studio-notes-gen.js").read_text(encoding="utf-8")
        self.assertIn("/api/notes/files/", js)
        self.assertIn("其他筆記檔案", js)


class CourseCompleteHookTest(unittest.IsolatedAsyncioTestCase):
    """Scenario 17b."""

    def setUp(self) -> None:
        """In-memory queue with two pending jobs for one course."""
        self.engine = create_db_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)
        with self.session_factory() as session:
            QueueRepository(session).enqueue_jobs(
                [
                    ArtifactJob(id=f"j{i}", course_code=CODE, lecture_no=i, artifact_type=ArtifactType.AUDIO)
                    for i in (1, 2)
                ]
            )

    @contextmanager
    def _provider(self) -> Iterator[QueueRepositoryProtocol]:
        """Yield a queue repository bound to a fresh session.

        Yields:
            QueueRepository instance.
        """
        with self.session_factory() as session:
            yield QueueRepository(session)
            session.commit()

    async def _run_next(self, pool: WorkerPool) -> None:
        """Claim and process the next pending job.

        Args:
            pool: Worker pool under test.
        """
        with self._provider() as repo:
            job = repo.claim_next_job(worker_id="w")
        assert job is not None
        await pool._process_job("w", job)

    async def test_course_complete_hook_fires_once_when_course_finishes(self) -> None:
        """Hook runs only after the last job; hook errors never break the queue."""
        calls: list[tuple[str, dict[str, int]]] = []

        def hook(code: str, counts: dict[str, int]) -> None:
            calls.append((code, counts))
            raise RuntimeError("notification failed")

        async def executor(job: ArtifactJob) -> str:
            return f"/tmp/{job.id}.m4a"

        pool = WorkerPool(self._provider, executor, concurrency=1)
        pool.on_course_complete = hook
        await self._run_next(pool)
        self.assertEqual(calls, [])
        await self._run_next(pool)
        self.assertEqual(calls, [(CODE, {"done": 2})])

        cfg_off = AppConfig(data_dir=Path("/tmp/x"), notify_on_complete=False)
        self.assertIsNone(course_complete_hook(cfg_off, mock.Mock()))
        cfg_on = AppConfig(data_dir=Path("/tmp/x"), notify_on_complete=True)
        send = mock.Mock()
        notify = course_complete_hook(cfg_on, send)
        assert notify is not None
        notify(CODE, {"done": 2, "failed": 1})
        title, message = send.call_args.args
        self.assertIn(CODE, message)
        self.assertIn("1 項需處理", message)


class VersionedAdoptTest(_Base):
    """Scenario 17c."""

    def test_adopt_outputs_includes_regenerated_versions(self) -> None:
        """v1 and v2 files become separate done jobs; a rerun skips everything."""
        lec = self.study_dir / "03 Notes" / "NotebookLM" / "01_Intro"
        lec.mkdir(parents=True)
        for name in ("infographic.png", "infographic_v2.png", "infographic_v2_A4.pdf", "quiz_1_quiz.json"):
            (lec / name).write_text("x", encoding="utf-8")
        (lec / "quiz_1_v2_quiz.json").write_text("{}", encoding="utf-8")
        with self.session_factory() as session:
            svc = AdoptOutputsService(self.cfg, CourseRepository(session), QueueRepository(session))
            res = svc.adopt_existing_outputs(CODE, dry_run=False)
            self.assertEqual(res["unmapped_files"], [])
            jobs = {
                (j.artifact_type.value, j.version)
                for j in QueueRepository(session).list_jobs(course_code=CODE)
            }
            self.assertEqual(jobs, {("infographic", 1), ("infographic", 2), ("quiz_1", 1), ("quiz_1", 2)})
            again = svc.adopt_existing_outputs(CODE, dry_run=True)
            self.assertEqual((again["would_create"], again["would_skip"]), (0, 4))


class BackupsTest(_Base):
    """Scenario 17d."""

    def test_backups_list_and_prune_move_to_deleted(self) -> None:
        """Preview moves nothing; apply moves the oldest into deleted/backups; invalid keep is refused."""
        root = self.cfg.data_dir / "backups"
        names = [f"db-20261125-0{i}0000" for i in range(1, 7)]
        for name in names:
            (root / name).mkdir(parents=True)
            (root / name / "app.db").write_bytes(b"x" * 10)
        client = TestClient(create_app(config=self.cfg))
        listed = client.get("/api/system/backups").json()["backups"]
        self.assertEqual([b["name"] for b in listed], list(reversed(names)))
        preview = client.post("/api/system/backups/prune", json={"keep": 5, "dry_run": True}).json()
        self.assertEqual(preview["to_move"], [names[0]])
        self.assertTrue((root / names[0]).is_dir())
        self.assertEqual(client.post("/api/system/backups/prune", json={"keep": 0}).status_code, 422)

        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertFalse(json.loads(tools["prune_backups"].fn(keep=5, dry_run=False))["confirmed"])
        self.assertTrue((root / names[0]).is_dir())
        applied = json.loads(tools["prune_backups"].fn(keep=5, dry_run=False, confirm=True))
        self.assertEqual(applied["moved"], [names[0]])
        self.assertFalse((root / names[0]).exists())
        self.assertTrue((self.cfg.data_dir / "deleted" / "backups" / names[0] / "app.db").is_file())
        js = (STATIC / "studio-library.js").read_text(encoding="utf-8")
        self.assertIn("/api/system/backups/prune", js)
        self.assertIn("backupsCard", (STATIC / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
