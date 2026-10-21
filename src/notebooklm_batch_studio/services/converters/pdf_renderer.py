"""PDF renderer: creates clean printable A4 documents via ReportLab with Chinese typography support."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from notebooklm_batch_studio.domain.models import Question, Quiz

logger = logging.getLogger(__name__)

CHOICE_LABELS = ["A", "B", "C", "D"]
_CHINESE_FONT_NAME: str | None = None


def resolve_chinese_font() -> str:
    """Find and register a system font that supports Traditional Chinese glyphs.

    Returns:
        The registered font family name for ReportLab styles.
    """
    global _CHINESE_FONT_NAME
    if _CHINESE_FONT_NAME is not None:
        return _CHINESE_FONT_NAME

    candidate_paths = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]

    for font_path in candidate_paths:
        if os.path.exists(font_path):
            try:
                font_name = "SystemChineseFont"
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                _CHINESE_FONT_NAME = font_name
                logger.info("Registered Chinese font: %s from %s", font_name, font_path)
                return font_name
            except Exception as err:
                logger.warning("Failed to register font %s: %s", font_path, err)

    _CHINESE_FONT_NAME = "Helvetica"
    logger.warning("No Chinese font found; falling back to Helvetica.")
    return _CHINESE_FONT_NAME


def _build_pdf_styles(font_name: str) -> dict[str, ParagraphStyle]:
    """Build typography and styling rules for Quiz PDF generation.

    Args:
        font_name: Registered font name capable of rendering Chinese characters.

    Returns:
        Dictionary mapping style names to ParagraphStyle objects.
    """
    return {
        "title": ParagraphStyle(
            "DocTitle",
            fontName=font_name,
            fontSize=18,
            leading=24,
            textColor=HexColor("#1A202C"),
            alignment=1,
            spaceAfter=10,
        ),
        "meta": ParagraphStyle(
            "DocMeta",
            fontName=font_name,
            fontSize=9,
            leading=14,
            textColor=HexColor("#718096"),
            alignment=1,
            spaceAfter=15,
        ),
        "stem": ParagraphStyle(
            "QuestionStem",
            fontName=font_name,
            fontSize=11,
            leading=16,
            textColor=HexColor("#2D3748"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "opt": ParagraphStyle(
            "OptionText",
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=HexColor("#4A5568"),
            leftIndent=15,
            spaceAfter=3,
        ),
        "ans": ParagraphStyle(
            "AnswerKey",
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=HexColor("#2B6CB0"),
            leftIndent=10,
            spaceBefore=4,
            spaceAfter=3,
        ),
        "rationale": ParagraphStyle(
            "RationaleText",
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=HexColor("#4A5568"),
            leftIndent=20,
            spaceAfter=2,
        ),
    }


def _build_question_flowables(
    idx: int,
    q: Question,
    styles: dict[str, ParagraphStyle],
    is_answer_key: bool,
) -> KeepTogether:
    """Build PDF flowable group for a single question.

    Args:
        idx: 1-based question number.
        q: Question entity.
        styles: Map of paragraph styles.
        is_answer_key: Whether to render answers and rationales.

    Returns:
        KeepTogether flowable containing stem and choices.
    """
    elements: list[Any] = [Paragraph(f"<b>{idx}.</b> {q.question}", styles["stem"])]

    for opt_idx, opt in enumerate(q.choices):
        letter = CHOICE_LABELS[opt_idx] if opt_idx < len(CHOICE_LABELS) else f"({opt_idx + 1})"
        elements.append(Paragraph(f"({letter}) {opt.text}", styles["opt"]))

    if is_answer_key:
        correct_letter = CHOICE_LABELS[q.answer_index] if q.answer_index < len(CHOICE_LABELS) else "?"
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>【正確答案】</b>: ({correct_letter})", styles["ans"]))

        for opt_idx, opt in enumerate(q.choices):
            letter = CHOICE_LABELS[opt_idx] if opt_idx < len(CHOICE_LABELS) else f"({opt_idx + 1})"
            tag = "正解" if opt_idx == q.answer_index else "析"
            if opt.rationale:
                elements.append(Paragraph(f"<b>[{tag}] ({letter})</b>: {opt.rationale}", styles["rationale"]))

        if q.hint:
            elements.append(Paragraph(f"<b>【思路提示】</b>: {q.hint}", styles["rationale"]))

    elements.append(Spacer(1, 10))
    return KeepTogether(elements)


def render_quiz_pdf(
    quiz: Quiz,
    output_path: str | Path,
    is_answer_key: bool = False,
    title: str | None = None,
) -> Path:
    """Generate a clean printable A4 PDF using ReportLab.

    Args:
        quiz: Domain Quiz entity.
        output_path: Target filesystem path for the PDF.
        is_answer_key: True to render answer key & rationale; False for student test paper.
        title: Optional custom document title.

    Returns:
        Path of the generated PDF file.
    """
    font_name = resolve_chinese_font()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = _build_pdf_styles(font_name)
    doc_title = title or (f"{quiz.title} (答案與詳解卷)" if is_answer_key else f"{quiz.title} (測驗卷)")
    meta_text = (
        f"課程：{quiz.course_code} | 講次：第 {quiz.lecture_no:02d} 講 | "
        f"版本：{quiz.variant} | 題數：{len(quiz.questions)} 題 | 來源：{quiz.source_pdf}"
    )

    story: list[Any] = [
        Paragraph(doc_title, styles["title"]),
        Paragraph(meta_text, styles["meta"]),
        HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=15),
    ]

    for idx, q in enumerate(quiz.questions, start=1):
        story.append(_build_question_flowables(idx, q, styles, is_answer_key))

    doc.build(story)
    logger.info("Generated PDF (%s) at %s", "Answer" if is_answer_key else "Exam", out)
    return out
