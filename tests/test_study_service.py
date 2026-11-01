"""Unit and integration tests for the Student Study Portal and Anki integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.models import CourseRecord
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.services.study_service import StudyTrackerService


class TestStudyService(unittest.TestCase):
    """Test suite for StudyTrackerService and StudyRepository."""

    def setUp(self) -> None:
        """Create an in-memory SQLite database and repository."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(bind=self.engine)

        # Seed course record
        course = CourseRecord(
            code="CS101",
            name="Introduction to Computer Science",
            source_dir="/dummy",
            notebook_id="nb-123",
        )
        self.session.add(course)
        self.session.commit()

        self.repo = StudyRepository(self.session)
        self.service = StudyTrackerService(study_repo=self.repo)

    def tearDown(self) -> None:
        """Clean up the database session."""
        self.session.close()

    def test_record_attempt_and_list_history(self) -> None:
        """Verify recording quiz attempts and retrieving study history."""
        attempt = self.service.record_quiz_attempt(
            course_code="CS101",
            lecture_no=1,
            quiz_variant="academic",
            score=8,
            total_questions=10,
            mistakes_data=[
                {
                    "question_text": "What is the time complexity of binary search?",
                    "choices": ["O(n)", "O(log n)", "O(n^2)", "O(1)"],
                    "correct_index": 1,
                    "selected_index": 0,
                    "explanation": "Binary search halves the search space each step.",
                }
            ],
        )
        self.assertIsNotNone(attempt.id)
        self.assertEqual(attempt.score, 8)
        self.assertEqual(len(attempt.mistakes), 1)

        history = self.service.get_study_history("CS101")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].score, 8)

    def test_weakness_tracking_and_resolution(self) -> None:
        """Verify mistake retrieval and resolution in the weakness notebook."""
        self.service.record_quiz_attempt(
            course_code="CS101",
            lecture_no=2,
            quiz_variant="concept",
            score=4,
            total_questions=5,
            mistakes_data=[
                {
                    "question_text": "Which structure uses LIFO?",
                    "choices": ["Queue", "Stack", "Array", "Tree"],
                    "correct_index": 1,
                    "selected_index": 0,
                    "explanation": "Stack uses Last-In First-Out.",
                }
            ],
        )

        unresolved = self.service.get_weaknesses("CS101", only_unresolved=True)
        self.assertEqual(len(unresolved), 1)
        mistake_id = unresolved[0].id

        # Resolve mistake
        resolved = self.service.resolve_weakness(mistake_id)
        self.assertTrue(resolved)

        # Confirm no longer in unresolved
        unresolved_after = self.service.get_weaknesses("CS101", only_unresolved=True)
        self.assertEqual(len(unresolved_after), 0)

        # But still accessible in all mistakes
        all_mistakes = self.service.get_weaknesses("CS101", only_unresolved=False)
        self.assertEqual(len(all_mistakes), 1)
        self.assertTrue(all_mistakes[0].is_resolved)

    def test_export_weaknesses_to_anki_csv(self) -> None:
        """Verify exporting weakness notebook mistakes to Anki CSV."""
        self.service.record_quiz_attempt(
            course_code="CS101",
            lecture_no=1,
            quiz_variant="academic",
            score=9,
            total_questions=10,
            mistakes_data=[
                {
                    "question_text": "What is Amortized Analysis?",
                    "choices": [
                        "Average case",
                        "Guaranteed average over sequence",
                        "Worst case",
                        "Best case",
                    ],
                    "correct_index": 1,
                    "selected_index": 0,
                    "explanation": "Amortized analysis averages worst-case operations over a sequence.",
                }
            ],
        )

        csv_text = self.service.export_weaknesses_to_anki_csv("CS101", lecture_no=1)
        self.assertIn("#separator:Comma", csv_text)
        self.assertIn("#html:true", csv_text)
        self.assertIn("Amortized Analysis", csv_text)
        self.assertIn("正確解答：選項 B", csv_text)
        self.assertIn("CS101 Weakness L01", csv_text)


class TestStudyApiEndpoints(unittest.TestCase):
    """Test suite for HTTP study portal endpoints."""

    def setUp(self) -> None:
        """Initialize test client with temporary database."""
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.config = AppConfig(
            database_url=f"sqlite:///{db_path}",
            data_dir=Path(self.temp_dir.name),
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.engine = create_engine(self.config.database_url)
        Base.metadata.create_all(self.engine)
        self.session = Session(bind=self.engine)

        course = CourseRecord(
            code="BIO101",
            name="General Biology",
            source_dir="/dummy",
            notebook_id="nb-bio",
        )
        self.session.add(course)
        self.session.commit()

        repo = StudyRepository(self.session)
        study_service = StudyTrackerService(study_repo=repo, config=self.config)
        app = create_app(config=self.config, study_service=study_service)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """Clean up resources."""
        self.session.close()
        self.temp_dir.cleanup()

    def test_post_attempt_and_get_endpoints(self) -> None:
        """Test full cycle: POST attempt -> GET history -> GET weaknesses -> GET Anki CSV."""
        payload = {
            "lecture_no": 1,
            "quiz_variant": "academic",
            "score": 9,
            "total_questions": 10,
            "mistakes": [
                {
                    "question_text": "Which organelle produces ATP?",
                    "choices": ["Ribosome", "Mitochondria", "Golgi", "Nucleus"],
                    "correct_index": 1,
                    "selected_index": 0,
                    "explanation": "Mitochondria performs cellular respiration.",
                }
            ],
        }
        resp = self.client.post("/api/courses/BIO101/study/quiz-attempts", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["score"], 9)

        # GET history
        hist_resp = self.client.get("/api/courses/BIO101/study/history")
        self.assertEqual(hist_resp.status_code, 200)
        self.assertEqual(len(hist_resp.json()), 1)

        # GET mistakes
        mistakes_resp = self.client.get("/api/courses/BIO101/study/mistakes")
        self.assertEqual(mistakes_resp.status_code, 200)
        mistakes = mistakes_resp.json()
        self.assertEqual(len(mistakes), 1)
        mistake_id = mistakes[0]["id"]

        # GET Anki CSV
        csv_resp = self.client.get("/api/courses/BIO101/study/mistakes/anki.csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("text/csv", csv_resp.headers["content-type"])
        self.assertIn("Mitochondria", csv_resp.text)

        # Resolve mistake
        res_resp = self.client.post(f"/api/courses/BIO101/study/mistakes/{mistake_id}/resolve")
        self.assertEqual(res_resp.status_code, 200)
        self.assertTrue(res_resp.json()["resolved"])

        # Confirm 0 unresolved mistakes
        empty_resp = self.client.get("/api/courses/BIO101/study/mistakes")
        self.assertEqual(len(empty_resp.json()), 0)


if __name__ == "__main__":
    unittest.main()
