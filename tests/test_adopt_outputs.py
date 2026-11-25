"""Tests for SPEC-015 adopting existing local NotebookLM outputs into artifact_jobs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    CourseStatus,
    JobStatus,
    Lecture,
    ProfileName,
)
from notebooklm_batch_studio.services.adopt_outputs import AdoptOutputsService

REAL_CH01_FILENAMES = (
    "115-1_L01_audio.m4a",
    "anki.csv",
    "flashcards.json",
    "infographic.png",
    "infographic_A4.pdf",
    "infographic_MacBookPro14.png",
    "infographic_iPadAir4.png",
    "mindmap.json",
    "mindmap.md",
    "mindmap.opml",
    "quiz.json",
    "quiz_1_interactive_quiz.html",
    "quiz_1_quiz.json",
    "quiz_1_答案卷.md",
    "quiz_1_答案卷.pdf",
    "quiz_1_題目卷.md",
    "quiz_1_題目卷.pdf",
    "quiz_2_interactive_quiz.html",
    "quiz_2_quiz.json",
    "quiz_2_答案卷.md",
    "quiz_2_答案卷.pdf",
    "quiz_2_題目卷.md",
    "quiz_2_題目卷.pdf",
    "quiz_3_interactive_quiz.html",
    "quiz_3_quiz.json",
    "quiz_3_答案卷.md",
    "quiz_3_答案卷.pdf",
    "quiz_3_題目卷.md",
    "quiz_3_題目卷.pdf",
    "study_guide.md",
    "答案卷.md",
)


class AdoptOutputsTests(unittest.TestCase):
    """BDD Scenario 15a-15d: adopt existing NotebookLM outputs without NotebookLM calls."""

    def setUp(self) -> None:
        """Create isolated DATA_DIR, database, and record-only course seeded with real filenames."""
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

        self.course_code = "115-1_CP30210"
        self.study_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        self.handouts_dir = self.study_dir / "02 Handouts"
        self.handouts_dir.mkdir(parents=True, exist_ok=True)
        (self.handouts_dir / "Ch01-Introduction-to-Scientific-Research.pdf").write_bytes(b"%PDF-1")

        self.nlm_root = self.study_dir / "03 Notes" / "NotebookLM"
        self.ch1_dir = self.nlm_root / "01_Introduction-to-Scientific-Research"
        self.ch1_dir.mkdir(parents=True, exist_ok=True)
        for fname in REAL_CH01_FILENAMES:
            (self.ch1_dir / fname).write_text("", encoding="utf-8")
        # Valid quiz content for Scenario 15c quiz reading and attempts.
        (self.ch1_dir / "quiz_1_題目卷.md").write_text("# Quiz 1\n\n1. Q1?", encoding="utf-8")
        (self.ch1_dir / "quiz_1_quiz.json").write_text(
            json.dumps(
                {
                    "title": "Quiz 1",
                    "questions": [{"question": "Q1?", "options": ["A", "B"], "answer": 0}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.ch1_dir / "stray_notes.txt").write_text("unmapped", encoding="utf-8")

        self.synth_dir = self.nlm_root / "_course_synthesis"
        self.synth_dir.mkdir(parents=True, exist_ok=True)
        for fname in (
            "115-1_Course_briefing_doc.md",
            "115-1_Course_briefing_doc_interactive.html",
            "course_mock_exam_quiz.json",
            "course_mock_exam_interactive_quiz.html",
            "mindmap.opml",
            "mindmap.json",
            "mindmap.md",
        ):
            (self.synth_dir / fname).write_text("", encoding="utf-8")

        with self.session_factory() as session:
            CourseRepository(session).save_course(
                Course(
                    code=self.course_code,
                    name="心理學研究法",
                    source_dir=str(self.study_dir),
                    study_dir=str(self.study_dir),
                    term="115-1",
                    course_no="CP30210",
                    profile=ProfileName.RECORD_ONLY,
                    status=CourseStatus.ACTIVE,
                    lectures=[
                        Lecture(
                            no=1,
                            topic="Introduction-to-Scientific-Research",
                            filename="Ch01-Introduction-to-Scientific-Research.pdf",
                            sha256="sha1",
                            category="02 Handouts",
                            relative_path="02 Handouts/Ch01-Introduction-to-Scientific-Research.pdf",
                        )
                    ],
                )
            )

    def tearDown(self) -> None:
        """Dispose engine and clean up temp directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_dry_run_maps_real_filenames_course_synthesis_and_reports_unmapped(self) -> None:
        """Scenario 15a: real 31 lecture filenames + _course_synthesis map cleanly; unmapped reported."""
        with self.session_factory() as session:
            result = AdoptOutputsService(
                self.cfg, CourseRepository(session), QueueRepository(session)
            ).adopt_existing_outputs(self.course_code, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["created"], 0)
            self.assertEqual(result["would_create"], 11)
            self.assertEqual(result["would_skip"], 0)
            self.assertEqual(
                result["unmapped_files"],
                ["01_Introduction-to-Scientific-Research/stray_notes.txt"],
            )

            lec_entry = next(entry for entry in result["lectures"] if entry["lecture_no"] == 1)
            matched_types = {m["artifact_type"]: m for m in lec_entry["matched"]}
            expected_lecture_types = {
                "audio",
                "flashcards",
                "infographic",
                "mind_map",
                "quiz_1",
                "quiz_2",
                "quiz_3",
                "study_guide",
            }
            self.assertEqual(set(matched_types.keys()), expected_lecture_types)
            self.assertEqual(Path(matched_types["audio"]["output_file"]).name, "115-1_L01_audio.m4a")
            self.assertEqual(Path(matched_types["quiz_1"]["output_file"]).name, "quiz_1_quiz.json")
            self.assertEqual(
                Path(matched_types["quiz_1"]["interactive_path"]).name, "quiz_1_interactive_quiz.html"
            )

            synth_entry = next(entry for entry in result["lectures"] if entry["lecture_no"] is None)
            synth_types = {m["artifact_type"]: m for m in synth_entry["matched"]}
            self.assertEqual(
                set(synth_types.keys()),
                {"course_reports_briefing", "course_mock_exam", "course_mind_map"},
            )
            self.assertEqual(
                Path(synth_types["course_reports_briefing"]["interactive_path"]).name,
                "115-1_Course_briefing_doc_interactive.html",
            )
            self.assertEqual(QueueRepository(session).list_jobs(course_code=self.course_code), [])

    def test_apply_creates_done_jobs_skips_existing_and_preserves_record_only_and_files(self) -> None:
        """Scenario 15b: dry_run=False inserts DONE v1 jobs, skips existing, never calls NotebookLM."""
        original_file_set = sorted(
            p.relative_to(self.nlm_root).as_posix() for p in self.nlm_root.rglob("*") if p.is_file()
        )
        with self.session_factory() as session:
            q_repo = QueueRepository(session)
            c_repo = CourseRepository(session)
            svc = AdoptOutputsService(self.cfg, c_repo, q_repo)
            q_repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="existing-sg",
                        course_code=self.course_code,
                        lecture_no=1,
                        artifact_type=ArtifactType.STUDY_GUIDE,
                        status=JobStatus.DONE,
                        version=1,
                        output_file="/custom/preserved_study_guide.md",
                    )
                ]
            )
            with mock.patch("notebooklm_batch_studio.adapters.notebooklm.client.NotebookLMAdapter") as nlm:
                res = svc.adopt_existing_outputs(self.course_code, dry_run=False)
                nlm.assert_not_called()

            self.assertFalse(res["dry_run"])
            self.assertEqual(res["created"], 10)
            self.assertEqual(res["skipped"], 1)

            jobs = q_repo.list_jobs(course_code=self.course_code)
            self.assertEqual(len(jobs), 11)
            for j in jobs:
                self.assertEqual(j.status, JobStatus.DONE)
                self.assertEqual(j.version, 1)
            sg = next(j for j in jobs if j.lecture_no == 1 and j.artifact_type == ArtifactType.STUDY_GUIDE)
            self.assertEqual(sg.output_file, "/custom/preserved_study_guide.md")

            course = c_repo.get_course(self.course_code)
            assert course is not None
            self.assertEqual(course.profile, ProfileName.RECORD_ONLY)
            self.assertIsNone(course.notebook_id)

            res_again = svc.adopt_existing_outputs(self.course_code, dry_run=False)
            self.assertEqual(res_again["created"], 0)
            self.assertEqual(res_again["skipped"], 11)

        after_file_set = sorted(
            p.relative_to(self.nlm_root).as_posix() for p in self.nlm_root.rglob("*") if p.is_file()
        )
        self.assertEqual(after_file_set, original_file_set)


if __name__ == "__main__":
    unittest.main()
