"""Render Q&A Markdown notes into clean Chinese-capable PDFs for Gemini Notebook upload."""

from __future__ import annotations

import html
import logging
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer

from notebooklm_batch_studio.services.converters.pdf_renderer import resolve_chinese_font

logger = logging.getLogger(__name__)


def _line_to_flowable(line: str, styles: dict[str, ParagraphStyle]) -> Paragraph | Spacer:
    """Convert one Markdown line into a styled ReportLab flowable.

    Args:
        line: Raw Markdown text line.
        styles: Dictionary of named ParagraphStyle instances.

    Returns:
        ReportLab Paragraph or Spacer flowable.
    """
    stripped = line.strip()
    if not stripped:
        return Spacer(1, 5)
    escaped = html.escape(stripped)
    if stripped.startswith("# "):
        return Paragraph(escaped[2:].strip(), styles["h1"])
    if stripped.startswith("## "):
        return Paragraph(escaped[3:].strip(), styles["h2"])
    if stripped.startswith("### "):
        return Paragraph(escaped[4:].strip(), styles["h3"])
    return Paragraph(escaped, styles["body"])


def render_markdown_to_pdf(title: str, markdown_text: str, output_pdf: Path) -> Path:
    """Compile a Markdown note (or bundled notes) into an A4 PDF file.

    Args:
        title: Document title displayed at top of the PDF.
        markdown_text: Source Markdown body text.
        output_pdf: Destination `.pdf` file path.

    Returns:
        Path to the generated PDF file.
    """
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    font = resolve_chinese_font()
    styles = {
        "h1": ParagraphStyle("NoteH1", fontName=font, fontSize=15, leading=21, textColor=HexColor("#1a202c")),
        "h2": ParagraphStyle("NoteH2", fontName=font, fontSize=12, leading=18, textColor=HexColor("#2d3748")),
        "h3": ParagraphStyle("NoteH3", fontName=font, fontSize=11, leading=16, textColor=HexColor("#4a5568")),
        "body": ParagraphStyle(
            "NoteBody", fontName=font, fontSize=10, leading=15, textColor=HexColor("#111827")
        ),
    }
    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=A4, leftMargin=45, rightMargin=45, topMargin=45, bottomMargin=45
    )
    story: list[Flowable] = [Paragraph(html.escape(title), styles["h1"]), Spacer(1, 10)]
    for line in markdown_text.splitlines():
        story.append(_line_to_flowable(line, styles))
    doc.build(story)
    logger.info("Rendered Markdown note PDF: %s", output_pdf)
    return output_pdf
