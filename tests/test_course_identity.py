"""Tests for domain/course_identity.py (SPEC-014 §5.1, ADR-014, ISSUE-058)."""

from __future__ import annotations

import unittest

from notebooklm_batch_studio.domain.course_identity import (
    TERM_PATTERN,
    CourseFolderInfo,
    make_course_code,
    notebook_title,
    parse_course_folder,
    split_course_code,
)
from notebooklm_batch_studio.domain.path_safety import PathSafetyError


class CourseIdentityTests(unittest.TestCase):
    """BDD scenarios for parsing school course folders and building term-scoped codes."""

    def test_parses_school_course_folders(self) -> None:
        """Scenario 1: school-formatted folders extract uppercase course_no and full name."""
        self.assertEqual(
            parse_course_folder("CP__30000-團體諮商"),
            CourseFolderInfo("CP30000", "團體諮商", True),
        )
        self.assertEqual(
            parse_course_folder("YY__5061AA-體育 (三)_超慢跑 AA"),
            CourseFolderInfo("YY5061AA", "體育 (三)_超慢跑 AA", True),
        )
        self.assertEqual(
            parse_course_folder("GC_68210-和 AI 一起寫程式"),
            CourseFolderInfo("GC68210", "和 AI 一起寫程式", True),
        )

    def test_non_course_folders(self) -> None:
        """Scenario 2: non-course folders and hidden files are flagged is_course=False."""
        for name in ("Course Outline", "專題", "115-1", ".DS_Store", "生涯諮商"):
            self.assertFalse(parse_course_folder(name).is_course, name)

    def test_codes(self) -> None:
        """Scenario 3: make/split course codes, notebook titles, and path-safety rejection."""
        self.assertEqual(make_course_code("115-1", "CP30000"), "115-1_CP30000")
        self.assertNotEqual(
            make_course_code("114-1", "CP30000"),
            make_course_code("115-1", "CP30000"),
        )
        self.assertEqual(split_course_code("115-1_CP30000"), ("115-1", "CP30000"))
        self.assertEqual(split_course_code("BIO101"), ("", "BIO101"))
        self.assertEqual(
            notebook_title("CP30000", "團體諮商", "115-1"),
            "[CP30000] 團體諮商 (115-1)",
        )
        self.assertRegex("115-1", TERM_PATTERN)
        with self.assertRaises(PathSafetyError):
            make_course_code("115-1", "CP/30000")
        with self.assertRaises(PathSafetyError):
            make_course_code("../115", "CP30000")


if __name__ == "__main__":
    unittest.main()
