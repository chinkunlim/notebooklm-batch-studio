"""SPEC-021: learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio."""

from __future__ import annotations

import logging
import unittest
from dataclasses import replace
from pathlib import Path

from notebooklm_batch_studio.domain.models import (
    ArtifactType,
    Course,
    Lecture,
    get_artifact_english_title,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.services.artifact_runner import SIMPLE_OUTPUTS
from notebooklm_batch_studio.services.course_settings import COURSE_TYPES
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course
from notebooklm_batch_studio.services.learning_site_prompt import render_site_prompt
from notebooklm_batch_studio.services.quota_planner import action_kind_for

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
FIXTURES = ROOT / "tests" / "fixtures"

LECTURES = [
    Lecture(no=n, topic=f"Topic-{n}", filename=f"Ch{n:02d}.pdf", sha256=str(n), source_id=f"src-{n}")
    for n in (1, 2, 3, 4, 5, 6, 13, 14, 16, 17)
]
LECTURES[0] = replace(LECTURES[0], topic="Career-Counseling-A-Life")
COURSE = Course(code="115-1_CP31000", name="生涯諮商與實務", source_dir="/tmp/x", lectures=LECTURES)


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


class PromptTest(unittest.TestCase):
    """Task 2: prompts come from section A (lecture) or B (whole book) of the bundled template."""

    def test_chapter_prompt_fills_section_a(self) -> None:
        """A lecture prompt starts with the trigger, names the lecture and leaves no placeholder."""
        text = render_site_prompt(COURSE, LECTURES[0])
        self.assertTrue(text.startswith("make me a site"))
        self.assertIn("「生涯諮商與實務」第 1 講「Career Counseling A Life」", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("整本書的互動學習網頁", text)

    def test_book_prompt_uses_section_b_with_range(self) -> None:
        """The whole-book prompt uses section B and states the lecture range and count."""
        text = render_site_prompt(COURSE, None)
        self.assertTrue(text.startswith("make me a site"))
        self.assertIn("整本書的互動學習網頁", text)
        self.assertIn("第 1–17 講（共 10 講）", text)
        self.assertNotIn("{{", text)

    def test_extra_instructions_are_appended(self) -> None:
        """Short custom instructions are appended as 補充要求."""
        text = render_site_prompt(COURSE, LECTURES[0], extra="多舉諮商實例")
        self.assertTrue(text.rstrip().endswith("補充要求：多舉諮商實例"))

    def test_full_custom_prompt_is_used_verbatim(self) -> None:
        """A custom prompt that already starts with the trigger replaces the template."""
        custom = "make me a site\n只做 3 題測驗"
        self.assertEqual(render_site_prompt(COURSE, LECTURES[0], extra=custom), custom)

    def test_planned_site_jobs_have_no_generic_prompt(self) -> None:
        """Planned site jobs carry no generic blueprint, which would otherwise become 補充要求."""
        course = replace(
            COURSE,
            selected_chapter_artifacts=["learning_site"],
            selected_course_artifacts=["course_learning_site"],
        )
        jobs = generate_jobs_for_course(course)
        self.assertEqual(len(jobs), 11)
        self.assertTrue(all(j.custom_prompt is None for j in jobs))


if __name__ == "__main__":
    unittest.main()
