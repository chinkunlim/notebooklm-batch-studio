"""Unit tests for artifact converters (Quiz, Flashcards, Mind Map).

Tests parsing of real NotebookLM output fixtures, deduplication and merging up to 30
questions, Markdown generation (題目卷.md & 答案卷.md), Anki CSV formatting,
OPML 2.0 XML tree structures, and ReportLab PDF rendering.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from notebooklm_batch_studio.adapters.converters.flashcard_converter import (
    parse_notebooklm_flashcards,
    to_anki_csv,
)
from notebooklm_batch_studio.adapters.converters.flashcard_converter import (
    to_json as flashcards_to_json,
)
from notebooklm_batch_studio.adapters.converters.mindmap_converter import (
    parse_notebooklm_mindmap,
    to_opml,
)
from notebooklm_batch_studio.adapters.converters.mindmap_converter import (
    to_json as mindmap_to_json,
)
from notebooklm_batch_studio.adapters.converters.mindmap_converter import (
    to_markdown as mindmap_to_markdown,
)
from notebooklm_batch_studio.adapters.converters.quiz_converter import (
    merge_and_deduplicate_quizzes,
    parse_notebooklm_quiz,
    to_answer_markdown,
    to_exam_markdown,
    to_pdf,
)
from notebooklm_batch_studio.adapters.converters.quiz_converter import (
    to_json as quiz_to_json,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestQuizConverter(unittest.TestCase):
    """Test suite for Quiz conversion, merging, and formatting."""

    def setUp(self) -> None:
        """Load fixture data before tests."""
        quiz_fixture_path = FIXTURES_DIR / "sample_quiz.json"
        with open(quiz_fixture_path, "r", encoding="utf-8") as f:
            self.raw_quiz_data = json.load(f)

    def test_parse_quiz_structure(self) -> None:
        """Verify parsing raw NotebookLM JSON into domain Quiz entity."""
        quiz = parse_notebooklm_quiz(
            raw_data=self.raw_quiz_data,
            course_code="BIO101",
            lecture_no=3,
            variant="1-基礎",
            source_pdf="03_cell_biology.pdf",
        )

        self.assertEqual(quiz.course_code, "BIO101")
        self.assertEqual(quiz.lecture_no, 3)
        self.assertEqual(len(quiz.questions), 10)

        # Check first question
        q1 = quiz.questions[0]
        self.assertEqual(q1.id, "BIO101-03-Q1-001")
        self.assertIn("流體鑲嵌模型", q1.question)
        self.assertEqual(len(q1.choices), 4)

        # Confirm answer index points to the correct choice
        self.assertTrue(q1.choices[q1.answer_index].is_correct)
        self.assertTrue(len(q1.choices[q1.answer_index].rationale) > 0)
        self.assertTrue(len(q1.hint) > 0)

    def test_merge_and_deduplicate_quizzes(self) -> None:
        """Verify merging multiple batches and filtering out duplicate questions."""
        quiz1 = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")
        quiz2 = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")

        # Merging identical quizzes should result in only 10 unique questions
        merged, is_complete = merge_and_deduplicate_quizzes([quiz1, quiz2], target_count=30)
        self.assertEqual(len(merged.questions), 10)
        self.assertFalse(is_complete)  # 10 < 30 -> needs review

        # Synthesize 3 batches with 30 unique questions
        synthesized_batches = []
        for batch_i in range(3):
            modified_raw = json.loads(json.dumps(self.raw_quiz_data))
            for q_idx, q in enumerate(modified_raw["questions"]):
                q["question"] = f"[Batch {batch_i} Q{q_idx}] {q['question']}"
            synthesized_batches.append(parse_notebooklm_quiz(modified_raw, "BIO101", 3, "1-基礎", "03.pdf"))

        merged_30, is_complete_30 = merge_and_deduplicate_quizzes(synthesized_batches, target_count=30)
        self.assertEqual(len(merged_30.questions), 30)
        self.assertTrue(is_complete_30)
        # Check re-indexing
        self.assertEqual(merged_30.questions[0].id, "BIO101-03-Q1-001")
        self.assertEqual(merged_30.questions[29].id, "BIO101-03-Q1-030")

    def test_exam_markdown_has_no_answers(self) -> None:
        """題目卷.md must strictly contain NO answers, rationales, or correctness indicators."""
        quiz = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")
        md = to_exam_markdown(quiz)

        self.assertIn("# 細胞膜 測驗 — 題目卷", md)
        self.assertIn("### 第 1 題", md)
        self.assertIn("- **(A)**", md)
        self.assertIn("- **(B)**", md)

        # Must NOT leak answers
        self.assertNotIn("【正確解答】", md)
        self.assertNotIn("各選項詳解", md)
        self.assertNotIn("✅", md)
        self.assertNotIn("正解說明", md)

    def test_answer_markdown_contains_full_pedagogical_details(self) -> None:
        """答案卷.md must contain answers, rationales for all choices, hints, and marks."""
        quiz = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")
        md = to_answer_markdown(quiz)

        self.assertIn("# 細胞膜 測驗 — 答案與詳解卷", md)
        self.assertIn("【正確解答】", md)
        self.assertIn("【各選項詳解】", md)
        self.assertIn("【解題思路與提示】", md)
        self.assertIn("✅", md)

    def test_quiz_json_serialization(self) -> None:
        """Verify serialization into uniform JSON schema."""
        quiz = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")
        json_str = quiz_to_json(quiz)
        loaded = json.loads(json_str)

        self.assertEqual(loaded["course_code"], "BIO101")
        self.assertEqual(loaded["questions_count"], 10)
        self.assertEqual(len(loaded["questions"][0]["choices"]), 4)

    def test_pdf_generation(self) -> None:
        """Verify PDF output generation using ReportLab."""
        quiz = parse_notebooklm_quiz(self.raw_quiz_data, "BIO101", 3, "1-基礎", "03.pdf")
        with tempfile.TemporaryDirectory() as tmpdir:
            exam_pdf = Path(tmpdir) / "exam.pdf"
            answer_pdf = Path(tmpdir) / "answer.pdf"

            to_pdf(quiz, exam_pdf, is_answer_key=False)
            to_pdf(quiz, answer_pdf, is_answer_key=True)

            self.assertTrue(exam_pdf.exists())
            self.assertTrue(exam_pdf.stat().st_size > 1000)

            self.assertTrue(answer_pdf.exists())
            self.assertTrue(answer_pdf.stat().st_size > 1000)


class TestFlashcardsConverter(unittest.TestCase):
    """Test suite for Flashcards parsing, JSON serialization, and Anki CSV generation."""

    def setUp(self) -> None:
        """Load flashcard fixture data before tests."""
        fc_fixture_path = FIXTURES_DIR / "sample_flashcards.json"
        with open(fc_fixture_path, "r", encoding="utf-8") as f:
            self.raw_fc_data = json.load(f)

    def test_parse_flashcards(self) -> None:
        """Verify parsing flashcard blocks into Flashcard entities."""
        cards = parse_notebooklm_flashcards(self.raw_fc_data)
        self.assertEqual(len(cards), 50)

        card1 = cards[0]
        self.assertIn("流體鑲嵌模型", card1.front)
        self.assertIn("磷脂雙層", card1.back)

    def test_flashcards_json_export(self) -> None:
        """Verify JSON export schema."""
        cards = parse_notebooklm_flashcards(self.raw_fc_data)
        out_json = flashcards_to_json(cards, title="Cell Biology Flashcards")
        parsed = json.loads(out_json)

        self.assertEqual(parsed["cards_count"], 50)
        self.assertEqual(parsed["title"], "Cell Biology Flashcards")

    def test_anki_csv_export(self) -> None:
        """Verify Anki-compatible CSV generation with headers and tags."""
        cards = parse_notebooklm_flashcards(self.raw_fc_data)[:5]
        csv_content = to_anki_csv(cards, tags=["BIO101", "Lecture 03"])

        lines = csv_content.strip().split("\n")
        # Check Anki directives
        self.assertEqual(lines[0], "#separator:Comma")
        self.assertEqual(lines[1], "#html:true")
        self.assertEqual(lines[2], "#tags column:3")

        # Check data row
        self.assertTrue(len(lines) >= 4)
        first_card_row = lines[3]
        self.assertIn("BIO101 Lecture_03", first_card_row)


class TestMindMapConverter(unittest.TestCase):
    """Test suite for Mind Map tree parsing, OPML 2.0 XML, and Markdown outlines."""

    def setUp(self) -> None:
        """Load mind map fixture data before tests."""
        mm_fixture_path = FIXTURES_DIR / "sample_mindmap.json"
        with open(mm_fixture_path, "r", encoding="utf-8") as f:
            self.raw_mm_data = json.load(f)

    def test_parse_mindmap(self) -> None:
        """Verify recursive parsing of mind map JSON tree."""
        root = parse_notebooklm_mindmap(self.raw_mm_data)
        self.assertEqual(root.title, "細胞膜結構與運輸")
        self.assertTrue(len(root.children) > 0)
        self.assertEqual(root.children[0].title, "流體鑲嵌模型")

    def test_opml_export_validity(self) -> None:
        """Verify that exported OPML is valid XML with outline nesting."""
        root = parse_notebooklm_mindmap(self.raw_mm_data)
        opml_xml = to_opml(root, title="細胞膜結構與運輸")

        # Ensure valid XML syntax
        xml_tree = ET.fromstring(opml_xml)
        self.assertEqual(xml_tree.tag, "opml")
        self.assertEqual(xml_tree.attrib.get("version"), "2.0")

        head = xml_tree.find("head")
        self.assertIsNotNone(head)
        title_elem = head.find("title") if head is not None else None
        self.assertIsNotNone(title_elem)
        if title_elem is not None:
            self.assertEqual(title_elem.text, "細胞膜結構與運輸")

        body = xml_tree.find("body")
        self.assertIsNotNone(body)
        outlines = body.findall("outline") if body is not None else []
        self.assertTrue(len(outlines) > 0)

    def test_markdown_export(self) -> None:
        """Verify hierarchical markdown bullet outline."""
        root = parse_notebooklm_mindmap(self.raw_mm_data)
        md = mindmap_to_markdown(root)

        self.assertTrue(md.startswith("# 細胞膜結構與運輸"))
        self.assertIn("- 流體鑲嵌模型", md)
        self.assertIn("  - 提出者與年代", md)

    def test_mindmap_json_export(self) -> None:
        """Verify uniform JSON structure."""
        root = parse_notebooklm_mindmap(self.raw_mm_data)
        json_str = mindmap_to_json(root)
        loaded = json.loads(json_str)

        self.assertEqual(loaded["title"], "細胞膜結構與運輸")
        self.assertTrue(isinstance(loaded["children"], list))


if __name__ == "__main__":
    unittest.main()
