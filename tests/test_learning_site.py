"""SPEC-021: learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio."""

from __future__ import annotations

import logging
import unittest
from pathlib import Path

from notebooklm_batch_studio.domain.models import ArtifactType, get_artifact_english_title
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.services.artifact_runner import SIMPLE_OUTPUTS
from notebooklm_batch_studio.services.course_settings import COURSE_TYPES
from notebooklm_batch_studio.services.quota_planner import action_kind_for

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
FIXTURES = ROOT / "tests" / "fixtures"


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


if __name__ == "__main__":
    unittest.main()
