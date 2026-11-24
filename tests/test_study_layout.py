"""Tests for domain/study_layout.py and plural category rules (SPEC-014 §5.2, ADR-014)."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.domain.study_layout import (
    DEFAULT_LAYOUT,
    CategoryRole,
    layout_from_names,
)
from notebooklm_batch_studio.services.course_parser import scan_course_directory


class StudyLayoutTests(unittest.TestCase):
    """BDD scenarios for study category roles, aliases, and absence of hardcoded singular literals."""

    def test_singular_and_plural_handouts_merged(self) -> None:
        """Scenario 4a: singular and plural Handout dirs merge; non-PDFs are excluded from lectures."""
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "CP__30000-團體諮商"
            (course / "02 Handout").mkdir(parents=True)
            (course / "02 Handouts" / "sub").mkdir(parents=True)
            (course / "02 Handout" / "a.pdf").write_bytes(b"%PDF-1.4\na")
            (course / "02 Handouts" / "sub" / "b.pdf").write_bytes(b"%PDF-1.4\nb")
            (course / "02 Handouts" / "c.pptx").write_bytes(b"pptx-bytes")

            self.assertEqual(
                {d.name for d in DEFAULT_LAYOUT.category_dirs(course, CategoryRole.HANDOUTS)},
                {"02 Handout", "02 Handouts"},
            )
            lectures = scan_course_directory(course).lectures
            self.assertEqual(sorted(lec.filename for lec in lectures), ["a.pdf", "b.pdf"])
            self.assertEqual(
                [lec.relative_path for lec in lectures if lec.filename == "b.pdf"],
                ["02 Handouts/sub/b.pdf"],
            )

    def test_materials_are_not_lectures(self) -> None:
        """Scenario 4b: PDFs in 01 Materials are textbooks and do not become lectures."""
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "CP__30000-團體諮商"
            (course / "01 Materials").mkdir(parents=True)
            (course / "01 Material").mkdir(parents=True)
            (course / "02 Handouts").mkdir(parents=True)
            (course / "01 Materials" / "textbook.pdf").write_bytes(b"%PDF-1.4\ntextbook")
            (course / "01 Material" / "paper.pdf").write_bytes(b"%PDF-1.4\npaper")
            (course / "02 Handouts" / "w1.pdf").write_bytes(b"%PDF-1.4\nw1")

            lectures = scan_course_directory(course).lectures
            self.assertEqual([lec.filename for lec in lectures], ["w1.pdf"])

    def test_ensure_tree_respects_alias(self) -> None:
        """Scenario 5a: ensure_tree skips creating plural dir when singular alias exists."""
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "CP__30000-團體諮商"
            (course / "01 Material").mkdir(parents=True)
            DEFAULT_LAYOUT.ensure_tree(course)
            self.assertFalse((course / "01 Materials").exists())
            self.assertTrue((course / "05 Assignments").is_dir())

    def test_role_of_and_custom_names(self) -> None:
        """Scenario 5b: role_of recognizes aliases; layout_from_names validates count."""
        self.assertEqual(DEFAULT_LAYOUT.role_of("02 Handout"), CategoryRole.HANDOUTS)
        self.assertEqual(DEFAULT_LAYOUT.role_of("02 Handouts"), CategoryRole.HANDOUTS)
        self.assertEqual(DEFAULT_LAYOUT.role_of("01 Material"), CategoryRole.MATERIALS)
        custom = layout_from_names("A, B, C, D, E")
        self.assertEqual(custom.names[CategoryRole.HANDOUTS], "B")
        self.assertEqual(custom.role_of("B"), CategoryRole.HANDOUTS)
        with self.assertRaises(ValueError):
            layout_from_names("A, B")

    def test_no_hardcoded_category_literals_left(self) -> None:
        """Scenario 5c: no hardcoded singular '01 Material' or '02 Handout' outside study_layout.py."""
        hits = [
            str(f)
            for f in Path("src/notebooklm_batch_studio").rglob("*")
            if f.suffix in {".py", ".js", ".html"}
            and f.name != "study_layout.py"
            and re.search(r"0[12] (Material|Handout)\b(?!s)", f.read_text(encoding="utf-8"))
        ]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
