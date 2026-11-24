"""Tests for Task 15 dry-run-first legacy data consolidation and ADR-015 exclusive guards."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import select
from watchdog.events import FileCreatedEvent

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.consolidation_repo import ConsolidationRepository
from notebooklm_batch_studio.adapters.db.course_identity_repo import CourseIdentityRepository
from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseRecord,
    LectureRecord,
    LiteratureItemRecord,
)
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.domain.models import Course, CourseStatus, JobStatus, Lecture
from notebooklm_batch_studio.domain.path_safety import is_within
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.legacy_consolidation import (
    ConsolidationDeps,
    ConsolidationRequest,
    ConsolidationStep,
    apply_consolidation,
    plan_consolidation,
    save_consolidation_report,
)
from notebooklm_batch_studio.services.watcher import CoursePdfEventHandler


class LegacyConsolidationTests(unittest.TestCase):
    """BDD Scenario 14a-14d: dry-run planning, apply, rollback, and exclusive/watcher guards."""

    def setUp(self) -> None:
        """Seed an isolated temporary DATA_DIR mimicking real legacy + study tree structures."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        self.legacy_notes_root = root / "note-studio" / "output" / "courses"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            legacy_note_studio_dir=self.legacy_notes_root,
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

        # 1. Course `115-1` living in `study/115-1/生涯諮商` with singular category folders + collision.
        self.old_career_dir = self.cfg.study_root_dir / "115-1" / "生涯諮商"
        (self.old_career_dir / "01 Material").mkdir(parents=True, exist_ok=True)
        (self.old_career_dir / "01 Material" / "paper.pdf").write_bytes(b"%PDF-ref")
        (self.old_career_dir / "02 Handout").mkdir(parents=True, exist_ok=True)
        (self.old_career_dir / "02 Handout" / "ch01.pdf").write_bytes(b"%PDF-singular")
        (self.old_career_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (self.old_career_dir / "02 Handouts" / "ch01.pdf").write_bytes(b"%PDF-existing")
        guide = self.old_career_dir / "03 Notes" / "NotebookLM" / "01_ch01" / "study_guide.md"
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text("# 生涯諮商第一章導論", encoding="utf-8")
        quiz_html = guide.parent / "quiz.html"
        quiz_html.write_text("<html>quiz</html>", encoding="utf-8")
        existing_ns = self.old_career_dir / "03 Notes" / "NoteStudio" / "ch01_導論_學習筆記.md"
        existing_ns.parent.mkdir(parents=True, exist_ok=True)
        existing_ns.write_text("# Existing Ch01", encoding="utf-8")

        # NoteStudio state file pointing to old study directory path.
        self.note_state_file = self.cfg.notes_state_dir / "115-1.json"
        self.note_state_file.parent.mkdir(parents=True, exist_ok=True)
        self.note_state_file.write_text(
            json.dumps(
                {
                    "course_key": "115-1",
                    "chapters": {
                        "ch01": {"status": "done", "stitched_path": str(existing_ns)},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # 2. Course `115-1_CP30210` with leftover PDFs inside `input/courses/CP__30210-心理學研究法`.
        self.research_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        (self.research_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (self.cfg.courses_input_dir / "CP__30210-心理學研究法").mkdir(parents=True, exist_ok=True)
        (self.cfg.courses_input_dir / "CP__30210-心理學研究法" / "01.pdf").write_bytes(b"%PDF-r1")

        # 3. Loose folder `midterm-submission/` in DATA_DIR.
        self.midterm_dir = self.cfg.data_dir / "midterm-submission"
        self.midterm_dir.mkdir(parents=True, exist_ok=True)
        (self.midterm_dir / "report.pdf").write_bytes(b"%PDF-midterm")

        # 4. Legacy note-studio folder with both colliding and new notes.
        ns_src = self.legacy_notes_root / "生涯諮商與實務"
        ns_src.mkdir(parents=True, exist_ok=True)
        (ns_src / "ch01_導論_學習筆記.md").write_text("# Duplicate Ch01", encoding="utf-8")
        (ns_src / "ch02_生涯理論_學習筆記.md").write_text("# Legacy Ch02 Note", encoding="utf-8")

        # 5. Deleted trash directory containing JSON/MD/PDF files.
        self.deleted_sample = self.cfg.deleted_dir / "115-1-20261112-182701"
        self.deleted_sample.mkdir(parents=True, exist_ok=True)
        (self.deleted_sample / "quiz.json").write_text('{"q": 1}', encoding="utf-8")
        (self.deleted_sample / "study_guide.md").write_text("# Deleted Guide", encoding="utf-8")
        (self.deleted_sample / "心理學研究法.pdf").write_bytes(b"%PDF-deleted")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1",
                    name="生涯諮商",
                    source_dir=str(self.old_career_dir),
                    study_dir=str(self.old_career_dir),
                    term="115-1",
                    status=CourseStatus.ACTIVE,
                    lectures=[
                        Lecture(
                            no=1,
                            topic="導論",
                            filename="ch01.pdf",
                            sha256="sha1",
                            category="02 Handout",
                            relative_path="02 Handout/ch01.pdf",
                        )
                    ],
                )
            )
            c_repo.save_course(
                Course(
                    code="115-1_CP30210",
                    name="心理學研究法",
                    source_dir=str(self.research_dir),
                    study_dir=str(self.research_dir),
                    term="115-1",
                    course_no="CP30210",
                    status=CourseStatus.ACTIVE,
                )
            )
            session.add(
                ArtifactJobRecord(
                    id="job-1",
                    course_code="115-1",
                    lecture_no=1,
                    artifact_type="study_guide",
                    status=JobStatus.DONE.value,
                    output_file=str(guide),
                    interactive_path=str(quiz_html),
                )
            )
            session.add(
                LiteratureItemRecord(
                    key="ref1",
                    input_text="APA ref",
                    course_code="115-1",
                    target_category="01 Material",
                    target_subfolder="Literature_Review",
                    file="paper.pdf",
                )
            )
            session.commit()

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _request(self) -> ConsolidationRequest:
        """Build full ConsolidationRequest mapping codes, folders, and assignments."""
        return ConsolidationRequest(
            code_maps={"115-1": "115-1_CP31000"},
            folder_maps={"115-1/生涯諮商": "CP__31000-生涯諮商與實務"},
            assignments=[
                ("midterm-submission", "115-1_CP31000", CategoryRole.ASSIGNMENTS, "期中專題"),
            ],
            note_course_maps={"生涯諮商與實務": "115-1_CP31000"},
        )

    def _deps(self, session, *, server_idle: bool = True, lit_locked: bool = False) -> ConsolidationDeps:
        """Build ConsolidationDeps bound to an active session."""
        lifecycle = CourseLifecycleService(
            CourseRepository(session),
            QueueRepository(session),
            CourseIdentityRepository(session),
            self.cfg,
        )
        return ConsolidationDeps(
            repo=ConsolidationRepository(session),
            lifecycle=lifecycle,
            check_server_idle=lambda: server_idle,
            acquire_lock=lambda: nullcontext(),
            is_literature_locked=lambda: lit_locked,
        )

    def test_dry_run_makes_no_changes_and_saves_plan_json_in_diagnostics(self) -> None:
        """Scenario 14a: default dry-run leaves files/DB untouched and writes JSON under diagnostics."""
        with self.session_factory() as session:
            steps = plan_consolidation(self.cfg, self._request(), repo=ConsolidationRepository(session))

        actions = {s.action for s in steps}
        self.assertTrue(
            {"rename_code", "rename_folder", "merge", "move", "import_notes", "inventory"} <= actions,
            actions,
        )
        report_path = save_consolidation_report(self.cfg, steps)
        self.assertTrue(is_within(report_path, self.cfg.diagnostics_reports_dir))
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["steps"]), len(steps))
        self.assertIn("source", payload["steps"][0])
        self.assertIn("target", payload["steps"][0])
        self.assertIn("note", payload["steps"][0])

        # Verify zero mutations on disk & DB
        self.assertTrue(self.old_career_dir.is_dir())
        new_career_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        self.assertFalse(new_career_dir.exists())
        self.assertTrue((self.cfg.courses_input_dir / "CP__30210-心理學研究法" / "01.pdf").is_file())
        self.assertTrue((self.deleted_sample / "quiz.json").is_file())
        with self.session_factory() as session:
            self.assertIsNotNone(session.get(CourseRecord, "115-1"))
            self.assertIsNone(session.get(CourseRecord, "115-1_CP31000"))

    def test_apply_consolidates_folder_rename_singular_merge_notes_assign_and_inventory(self) -> None:
        """Scenario 14b: --apply syncs folders, non-overwriting merges, DB prefixes, HTTP 200 & inventory."""
        with self.session_factory() as session:
            repo = ConsolidationRepository(session)
            steps = plan_consolidation(self.cfg, self._request(), repo=repo)
            summary = apply_consolidation(self.cfg, steps, deps=self._deps(session))

        self.assertGreaterEqual(summary["applied"], 5)
        new_career_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        self.assertTrue(new_career_dir.is_dir())
        self.assertFalse(self.old_career_dir.exists())

        # Singular category contents merged without overwriting; empty folder kept
        self.assertEqual((new_career_dir / "02 Handouts" / "ch01.pdf").read_bytes(), b"%PDF-existing")
        self.assertEqual((new_career_dir / "02 Handouts" / "ch01_1.pdf").read_bytes(), b"%PDF-singular")
        self.assertTrue((new_career_dir / "02 Handout").is_dir())
        self.assertEqual(list((new_career_dir / "02 Handout").iterdir()), [])
        self.assertTrue((new_career_dir / "01 Materials" / "paper.pdf").is_file())

        # input/courses, midterm assignment, legacy NoteStudio, and untouched deleted/
        self.assertTrue((self.research_dir / "02 Handouts" / "01.pdf").is_file())
        self.assertTrue((new_career_dir / "05 Assignments" / "期中專題" / "report.pdf").is_file())
        ns_dest = new_career_dir / "03 Notes" / "NoteStudio"
        self.assertEqual((ns_dest / "ch01_導論_學習筆記.md").read_text(encoding="utf-8"), "# Existing Ch01")
        self.assertTrue((ns_dest / "ch02_生涯理論_學習筆記.md").is_file())
        self.assertTrue((self.deleted_sample / "心理學研究法.pdf").is_file())

        # Note state JSON stitched_path rewritten
        renamed_state = json.loads((self.cfg.notes_state_dir / "115-1_CP31000.json").read_text("utf-8"))
        stitched = Path(renamed_state["chapters"]["ch01"]["stitched_path"])
        self.assertEqual(stitched, ns_dest / "ch01_導論_學習筆記.md")
        self.assertTrue(stitched.is_file())

        # Database paths and category columns updated
        with self.session_factory() as session:
            course = session.get(CourseRecord, "115-1_CP31000")
            self.assertIsNotNone(course)
            assert course is not None
            self.assertEqual(course.study_dir, str(new_career_dir))
            self.assertEqual(course.source_dir, str(new_career_dir))
            self.assertEqual(course.subject, "CP__31000-生涯諮商與實務")
            job = session.get(ArtifactJobRecord, "job-1")
            assert job is not None
            self.assertTrue((job.output_file or "").startswith(str(new_career_dir)))
            self.assertTrue((job.interactive_path or "").startswith(str(new_career_dir)))
            lec = session.scalar(select(LectureRecord).where(LectureRecord.course_code == "115-1_CP31000"))
            assert lec is not None
            self.assertEqual(lec.category, "02 Handouts")
            self.assertTrue(lec.relative_path.startswith("02 Handouts/"))
            lit = session.get(LiteratureItemRecord, "ref1")
            assert lit is not None
            self.assertEqual(lit.target_category, "01 Materials")

        # HTTP view route serves migrated artifact at new course code
        client = TestClient(create_app(config=self.cfg))
        resp = client.get("/api/artifacts/115-1_CP31000/view/01_ch01/study_guide.md")
        self.assertEqual(resp.status_code, 200)

    def test_folder_rename_midway_failure_rolls_back_db_notes_and_folder(self) -> None:
        """Scenario 14c: failure during folder rename restores old folder, note state JSON, and DB."""
        new_career_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        steps = [
            ConsolidationStep(
                action="rename_folder",
                source=str(self.old_career_dir),
                target=str(new_career_dir),
                note="rename folder test",
            )
        ]
        orig_note_text = self.note_state_file.read_text(encoding="utf-8")
        with self.session_factory() as session:
            deps = self._deps(session)
            with mock.patch.object(
                deps.repo, "rewrite_course_folder_paths", side_effect=RuntimeError("db fail")
            ):
                with self.assertRaises(RuntimeError):
                    apply_consolidation(self.cfg, steps, deps=deps)

        self.assertTrue(self.old_career_dir.is_dir())
        self.assertFalse(new_career_dir.exists())
        self.assertEqual(self.note_state_file.read_text(encoding="utf-8"), orig_note_text)
        with self.session_factory() as session:
            course = session.get(CourseRecord, "115-1")
            assert course is not None
            self.assertEqual(course.study_dir, str(self.old_career_dir))

    def test_apply_refuses_when_server_busy_or_active_job_and_watcher_respects_pause_sentinel(self) -> None:
        """Scenario 14d: refuse --apply on busy server/job/lock, and watcher skips events while paused."""
        steps = [
            ConsolidationStep(
                action="move",
                source=str(self.midterm_dir),
                target=str(self.old_career_dir / "05 Assignments" / "期中專題"),
                note="assign",
            )
        ]
        with self.session_factory() as session:
            with self.assertRaises(RuntimeError):
                apply_consolidation(self.cfg, steps, deps=self._deps(session, server_idle=False))
            with self.assertRaises(RuntimeError):
                apply_consolidation(self.cfg, steps, deps=self._deps(session, lit_locked=True))
            job = session.get(ArtifactJobRecord, "job-1")
            assert job is not None
            job.status = JobStatus.RUNNING.value
            session.commit()
            with self.assertRaises(RuntimeError):
                apply_consolidation(self.cfg, steps, deps=self._deps(session))

        # Watcher respects consolidate.pause sentinel
        pause_file = self.cfg.consolidate_pause_path
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.write_text("paused\n", encoding="utf-8")
        detected: list[tuple[Path, Path]] = []
        pdf_path = self.old_career_dir / "02 Handouts" / "new_watch.pdf"
        pdf_path.write_bytes(b"%PDF-watch")
        handler = CoursePdfEventHandler(
            watch_root=self.cfg.study_root_dir,
            resolve_course=lambda p: self.old_career_dir,
            on_pdf_detected=lambda c, p: detected.append((c, p)),
        )
        handler.set_pause_check(lambda: pause_file.exists())
        handler.on_created(FileCreatedEvent(str(pdf_path)))
        self.assertEqual(detected, [])
        os.unlink(pause_file)
        with mock.patch("notebooklm_batch_studio.services.watcher._wait_for_file_settled", return_value=True):
            handler.on_created(FileCreatedEvent(str(pdf_path)))
        self.assertEqual(len(detected), 1)

    def test_cli_consolidate_dry_run_save_plan_and_apply(self) -> None:
        """CLI `consolidate` prints row-by-row table on dry-run, saves plan, and applies when requested."""
        from notebooklm_batch_studio.entrypoints.cli import main

        with mock.patch("notebooklm_batch_studio.entrypoints.cli.load_config", return_value=self.cfg):
            rc_dry = main(
                [
                    "consolidate",
                    "--dry-run",
                    "--map",
                    "115-1=115-1_CP31000",
                    "--folder",
                    "115-1/生涯諮商=CP__31000-生涯諮商與實務",
                    "--assign",
                    "midterm-submission=115-1_CP31000:ASSIGNMENTS/期中專題",
                    "--note-map",
                    "生涯諮商與實務=115-1_CP31000",
                    "--save-plan",
                ]
            )
            self.assertEqual(rc_dry, 0)
            self.assertTrue(self.old_career_dir.is_dir())
            diag_files = list(self.cfg.diagnostics_reports_dir.glob("consolidate-dry-run-*.json"))
            self.assertEqual(len(diag_files), 1)

            with mock.patch(
                "notebooklm_batch_studio.entrypoints.cli_consolidate.port_is_free", return_value=True
            ):
                rc_apply = main(
                    [
                        "consolidate",
                        "--apply",
                        "--map",
                        "115-1=115-1_CP31000",
                        "--folder",
                        "115-1/生涯諮商=CP__31000-生涯諮商與實務",
                        "--assign",
                        "midterm-submission=115-1_CP31000:ASSIGNMENTS/期中專題",
                        "--note-map",
                        "生涯諮商與實務=115-1_CP31000",
                    ]
                )
            self.assertEqual(rc_apply, 0)
            self.assertTrue((self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務").is_dir())

    def test_restore_from_deleted_copies_without_removing_source_and_suffixes_collisions(
        self,
    ) -> None:
        """Deleted restores and --assign from deleted/ copy files safely with suffixing."""
        restore_src = self.deleted_sample / "115-1" / "01_Intro"
        restore_src.mkdir(parents=True, exist_ok=True)
        (restore_src / "study_guide.md").write_text("# Restored Intro", encoding="utf-8")
        (restore_src / "audio.m4a").write_bytes(b"M4A")
        existing_guide = self.research_dir / "03 Notes" / "NotebookLM" / "01_Intro" / "study_guide.md"
        existing_guide.parent.mkdir(parents=True, exist_ok=True)
        existing_guide.write_text("# Existing Intro", encoding="utf-8")

        deleted_pdf_src = self.deleted_sample / "extra.pdf"
        deleted_pdf_src.write_bytes(b"%PDF-deleted-extra")

        req = ConsolidationRequest(
            folder_maps={
                "115-1/GC__68210-和 AI 一起寫程式": "GC__68210-和 AI 一起寫程式",
            },
            assignments=[
                ("midterm-submission", "115-1_GC68210", CategoryRole.ASSIGNMENTS, "期中專題"),
                ("deleted/115-1-20261112-182701/extra.pdf", "115-1_CP30210", CategoryRole.MATERIALS, ""),
            ],
            restores=[
                (
                    "deleted/115-1-20261112-182701/115-1/01_Intro",
                    "115-1_CP30210",
                    CategoryRole.NOTES,
                    "NotebookLM/01_Intro",
                ),
            ],
        )
        with self.session_factory() as session:
            steps = plan_consolidation(self.cfg, req, repo=ConsolidationRepository(session))
            self.assertFalse(any(s.action == "rename_folder" for s in steps), steps)
            copy_steps = [s for s in steps if s.action == "copy"]
            self.assertEqual(len(copy_steps), 2, steps)
            summary = apply_consolidation(self.cfg, steps, deps=self._deps(session))

        self.assertGreaterEqual(summary.get("copy", 0), 2)
        # Sources inside deleted/ stay completely intact
        self.assertTrue((restore_src / "study_guide.md").is_file())
        self.assertTrue((restore_src / "audio.m4a").is_file())
        self.assertTrue(deleted_pdf_src.is_file())
        # Destinations get non-overwriting suffixed copies + unregistered target course dir received midterm
        self.assertEqual(existing_guide.read_text(encoding="utf-8"), "# Existing Intro")
        self.assertEqual(
            (existing_guide.parent / "study_guide_1.md").read_text(encoding="utf-8"), "# Restored Intro"
        )
        self.assertTrue((existing_guide.parent / "audio.m4a").is_file())
        self.assertTrue((self.research_dir / "01 Materials" / "extra.pdf").is_file())
        self.assertTrue(
            (
                self.cfg.study_root_dir
                / "115-1"
                / "GC__68210-和 AI 一起寫程式"
                / "05 Assignments"
                / "期中專題"
                / "report.pdf"
            ).is_file()
        )
        from notebooklm_batch_studio.entrypoints.cli import main

        with mock.patch("notebooklm_batch_studio.entrypoints.cli.load_config", return_value=self.cfg):
            rc = main(
                [
                    "consolidate",
                    "--dry-run",
                    "--restore",
                    "deleted/115-1-20261112-182701/115-1/01_Intro=115-1_CP30210:NOTES/NotebookLM/01_Intro",
                ]
            )
            self.assertEqual(rc, 0)

    def test_input_course_study_notes_subfolder_appears_in_inventory_and_supports_assign(self) -> None:
        """Non-PDF subfolders like input/courses/<course>/study-notes appear in inventory and assign."""
        legacy_in = self.cfg.courses_input_dir / "115-1 心理學研究法"
        sn_dir = legacy_in / "study-notes"
        (sn_dir / "output").mkdir(parents=True, exist_ok=True)
        (sn_dir / "STYLE_GUIDE.md").write_text("# Style Guide", encoding="utf-8")
        (sn_dir / "output" / "ch01.html").write_text("<h1>Ch01</h1>", encoding="utf-8")
        (legacy_in / "Ch01.pdf").write_bytes(b"%PDF-legacy-in")

        base_req = ConsolidationRequest(
            folder_maps={"115-1/CP__30210-心理學研究法": "CP__30210-心理學研究法"},
        )
        with self.session_factory() as session:
            steps = plan_consolidation(self.cfg, base_req, repo=ConsolidationRepository(session))

        inv_notes = [s for s in steps if s.action == "inventory" and s.source.endswith("study-notes")]
        self.assertEqual(len(inv_notes), 1, steps)
        self.assertIn("03 Notes/study-notes", inv_notes[0].target)
        self.assertIn("files=2", inv_notes[0].note)

        # Verify legacy folder name `115-1 心理學研究法` matches CP__30210-心理學研究法
        pdf_moves = [s for s in steps if s.action == "move" and s.source.endswith("Ch01.pdf")]
        self.assertEqual(len(pdf_moves), 1, steps)
        self.assertTrue(pdf_moves[0].target.endswith("CP__30210-心理學研究法/02 Handouts/Ch01.pdf"))

        assigned_req = ConsolidationRequest(
            folder_maps={"115-1/CP__30210-心理學研究法": "CP__30210-心理學研究法"},
            assignments=[
                (
                    "input/courses/115-1 心理學研究法/study-notes",
                    "115-1_CP30210",
                    CategoryRole.NOTES,
                    "study-notes",
                )
            ],
        )
        with self.session_factory() as session:
            steps2 = plan_consolidation(self.cfg, assigned_req, repo=ConsolidationRepository(session))
            self.assertFalse(
                any(s.action == "inventory" and s.source.endswith("study-notes") for s in steps2), steps2
            )
            apply_consolidation(self.cfg, steps2, deps=self._deps(session))

        dest_notes = self.research_dir / "03 Notes" / "study-notes"
        self.assertEqual((dest_notes / "STYLE_GUIDE.md").read_text(encoding="utf-8"), "# Style Guide")
        self.assertTrue((dest_notes / "output" / "ch01.html").is_file())

    def test_legacy_notes_imports_nested_md_preserving_relative_paths(self) -> None:
        """Legacy note-studio folders with nested .md trees (zero top-level .md) plan and copy recursively."""
        nested_ns = self.legacy_notes_root / "115-1 心理學研究法"
        nested_file = nested_ns / "學習筆記" / "原稿" / "Ch01_導論_學習筆記.md"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text("# Nested Ch01 Note", encoding="utf-8")
        hidden_file = nested_ns / ".hidden" / "secret.md"
        hidden_file.parent.mkdir(parents=True, exist_ok=True)
        hidden_file.write_text("# Should Skip", encoding="utf-8")
        pdf_file = nested_ns / "學習筆記" / "Ch01_導論.pdf"
        pdf_file.write_bytes(b"%PDF-note")

        req = ConsolidationRequest(
            note_course_maps={"115-1 心理學研究法": "115-1_CP30210"},
        )
        with self.session_factory() as session:
            steps = plan_consolidation(self.cfg, req, repo=ConsolidationRepository(session))
            import_steps = [
                s for s in steps if s.action == "import_notes" and s.source.endswith("115-1 心理學研究法")
            ]
            self.assertEqual(len(import_steps), 1, steps)
            self.assertIn("1 份", import_steps[0].note)
            apply_consolidation(self.cfg, steps, deps=self._deps(session))

        notes_root = self.research_dir / "03 Notes" / "NoteStudio"
        dest_note = notes_root / "學習筆記" / "原稿" / "Ch01_導論_學習筆記.md"
        self.assertTrue(dest_note.is_file())
        self.assertEqual(dest_note.read_text(encoding="utf-8"), "# Nested Ch01 Note")
        self.assertTrue(nested_file.is_file())
        self.assertFalse((notes_root / ".hidden" / "secret.md").exists())
        self.assertFalse((notes_root / "學習筆記" / "Ch01_導論.pdf").exists())


if __name__ == "__main__":
    unittest.main()
