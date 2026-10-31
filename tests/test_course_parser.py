"""Unit tests for course folder scanner, name parser, and course.toml serialization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.services.course_parser import (
    parse_course_folder_name,
    parse_lecture_filename,
    read_course_toml,
    scan_course_directory,
    write_course_toml,
)


class CourseParserTest(unittest.TestCase):
    """Verify smart course code inference, lecture filename parsing, and toml serialization."""

    def test_parse_course_folder_name(self) -> None:
        """Alphanumeric prefix is extracted as code; non-matching names fallback gracefully."""
        code, name = parse_course_folder_name("BIO101 普通生物學")
        self.assertEqual(code, "BIO101")
        self.assertEqual(name, "普通生物學")

        code2, name2 = parse_course_folder_name("CS50_Introduction to CS")
        self.assertEqual(code2, "CS50")
        self.assertEqual(name2, "Introduction to CS")

        code3, name3 = parse_course_folder_name("細胞生物學專題")
        self.assertEqual(code3, "細胞生物學專題")
        self.assertEqual(name3, "細胞生物學專題")

        code4, name4 = parse_course_folder_name("115-1 心理學研究法")
        self.assertEqual(code4, "115-1")
        self.assertEqual(name4, "心理學研究法")

    def test_parse_lecture_filename(self) -> None:
        """Lecture number and topic are extracted from various filename conventions."""
        no1, topic1 = parse_lecture_filename("03_細胞膜運輸.pdf", fallback_no=1)
        self.assertEqual(no1, 3)
        self.assertEqual(topic1, "細胞膜運輸")

        no2, topic2 = parse_lecture_filename("Lecture 05 - Photosynthesis.pdf", fallback_no=2)
        self.assertEqual(no2, 5)
        self.assertEqual(topic2, "Photosynthesis")

        no3, topic3 = parse_lecture_filename("GeneralOverview.pdf", fallback_no=9)
        self.assertEqual(no3, 9)
        self.assertEqual(topic3, "GeneralOverview")

        no4, topic4 = parse_lecture_filename("Ch04-Ethics.pdf", fallback_no=4)
        self.assertEqual(no4, 4)
        self.assertEqual(topic4, "Ethics")

    def test_scan_directory_and_deduplicate(self) -> None:
        """Scanning a directory extracts sorted lectures and deduplicates identical PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir) / "BIO200 分子生物學"
            dir_path.mkdir()

            pdf1 = dir_path / "01_DNA_Replication.pdf"
            pdf1.write_bytes(b"%PDF-1.4 dummy content A")

            pdf2 = dir_path / "02_Transcription.pdf"
            pdf2.write_bytes(b"%PDF-1.4 dummy content B")

            # Duplicate content of pdf1 with a different filename
            pdf_dup = dir_path / "03_Duplicate_DNA.pdf"
            pdf_dup.write_bytes(b"%PDF-1.4 dummy content A")

            course = scan_course_directory(dir_path)
            self.assertEqual(course.code, "BIO200")
            self.assertEqual(course.name, "分子生物學")
            # Only 2 unique lectures should be kept
            self.assertEqual(len(course.lectures), 2)
            self.assertEqual(course.lectures[0].topic, "DNA_Replication")
            self.assertEqual(course.lectures[1].topic, "Transcription")

    def test_course_toml_roundtrip(self) -> None:
        """Writing and reading course.toml preserves all settings and lecture overrides."""
        with tempfile.TemporaryDirectory() as temp_dir:
            toml_path = Path(temp_dir) / "course.toml"
            course = Course(
                code="BIO101",
                name="普通生物學",
                source_dir="/home/user/courses/bio101",
                notebook_id="nb-999",
                profile=ProfileName.FULL,
                language="zh-TW",
                exam_date="2026-12-15",
                watch=True,
                mock_exam_questions=40,
                lectures=[
                    Lecture(no=1, topic="細胞構造", filename="01_cell.pdf", sha256="h1"),
                    Lecture(no=2, topic="能量代謝", filename="02_energy.pdf", sha256="h2"),
                ],
            )
            write_course_toml(toml_path, course)

            data = read_course_toml(toml_path)
            self.assertEqual(data["code"], "BIO101")
            self.assertEqual(data["name"], "普通生物學")
            self.assertEqual(data["profile"], "full")
            self.assertEqual(data["notebook_id"], "nb-999")
            self.assertEqual(len(data["lectures"]), 2)
            self.assertEqual(data["lectures"][0]["topic"], "細胞構造")
