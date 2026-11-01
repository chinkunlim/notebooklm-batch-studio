"""Quiz converter: transforms NotebookLM raw quiz outputs into Markdown, PDF, and JSON.

Supports merging multiple 10-question extracts, deduplicating question stems,
generating student exam papers (題目卷.md, no answers) and teacher/study answer keys
(答案卷.md, full rationale per option and hints), plus printable PDFs via ReportLab.
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import Choice, Question, Quiz
from notebooklm_batch_studio.services.converters.pdf_renderer import render_quiz_pdf

logger = logging.getLogger(__name__)

CHOICE_LABELS = ["A", "B", "C", "D"]


def _parse_question_dict(
    q_dict: dict[str, Any],
    id_prefix: str,
    idx: int,
    source_pdf: str,
) -> Question | None:
    """Parse a single raw question dictionary into a Question entity.

    Args:
        q_dict: Raw question dictionary.
        id_prefix: Question ID prefix (e.g. 'BIO101-03-Q1').
        idx: 1-based question index.
        source_pdf: Original PDF filename.

    Returns:
        Populated Question entity, or None if invalid.
    """
    stem = str(q_dict.get("question", "")).strip()
    if not stem:
        return None

    raw_options = q_dict.get("answerOptions", [])
    choices: list[Choice] = []
    answer_index = 0

    for opt_idx, opt in enumerate(raw_options):
        if not isinstance(opt, dict):
            continue
        opt_text = str(opt.get("text", "")).strip()
        is_corr = bool(opt.get("isCorrect", False))
        rationale = str(opt.get("rationale", "")).strip()
        if is_corr:
            answer_index = opt_idx
        choices.append(Choice(text=opt_text, is_correct=is_corr, rationale=rationale))

    hint = str(q_dict.get("hint", "")).strip()
    explanation = choices[answer_index].rationale if choices and answer_index < len(choices) else ""
    q_id = f"{id_prefix}-{idx:03d}"

    return Question(
        id=q_id,
        question=stem,
        choices=choices,
        answer_index=answer_index,
        explanation=explanation,
        hint=hint,
        source=source_pdf,
    )


def parse_notebooklm_quiz(
    raw_data: dict[str, Any] | list[Any],
    course_code: str,
    lecture_no: int,
    variant: str = "1-基礎",
    source_pdf: str = "",
    title: str = "",
) -> Quiz:
    """Parse raw NotebookLM quiz JSON into a domain Quiz entity.

    Args:
        raw_data: Raw JSON dictionary or question list extracted from NotebookLM.
        course_code: Course identifier (e.g. BIO101).
        lecture_no: Sequence number of the lecture.
        variant: Quiz difficulty or variant label (e.g. 1-基礎, 2-理解, 3-模擬考).
        source_pdf: Source PDF file name.
        title: Optional custom quiz title.

    Returns:
        Domain Quiz entity populated with parsed questions.
    """
    if isinstance(raw_data, dict):
        raw_title = str(raw_data.get("title", ""))
        quiz_title = title or raw_title or f"[{lecture_no:02d}] Quiz {variant}"
        questions_raw = raw_data.get("questions", [])
    elif isinstance(raw_data, list):
        quiz_title = title or f"[{lecture_no:02d}] Quiz {variant}"
        questions_raw = raw_data
    else:
        questions_raw = []
        quiz_title = title or f"[{lecture_no:02d}] Quiz {variant}"

    parsed: list[Question] = []
    v_prefix = variant[:1] if variant else "1"
    id_prefix = f"{course_code}-{lecture_no:02d}-Q{v_prefix}"

    for idx, q_dict in enumerate(questions_raw, start=1):
        if isinstance(q_dict, dict):
            q_entity = _parse_question_dict(q_dict, id_prefix, idx, source_pdf)
            if q_entity:
                parsed.append(q_entity)

    return Quiz(
        course_code=course_code,
        lecture_no=lecture_no,
        variant=variant,
        title=quiz_title,
        source_pdf=source_pdf,
        prompt_version="1.0",
        questions=parsed,
    )


def _normalize_stem(text: str) -> str:
    """Normalize question stem for duplicate comparison.

    Args:
        text: Question stem text.

    Returns:
        Normalized string with punctuation and whitespace removed.
    """
    return re.sub(r"[\s\W_]+", "", text).lower()


def _collect_unique_questions(quizzes: list[Quiz]) -> list[Question]:
    """Collect questions across quiz batches while filtering out duplicates.

    Args:
        quizzes: List of Quiz batches.

    Returns:
        Deduplicated list of questions.
    """
    seen_stems: set[str] = set()
    deduped: list[Question] = []
    for qz in quizzes:
        for q in qz.questions:
            norm = _normalize_stem(q.question)
            if norm and norm not in seen_stems:
                seen_stems.add(norm)
                deduped.append(q)
    return deduped


def merge_and_deduplicate_quizzes(
    quizzes: list[Quiz],
    target_count: int = 30,
) -> tuple[Quiz, bool]:
    """Merge multiple Quiz batches, remove duplicate questions, and check target count.

    Args:
        quizzes: List of Quiz instances to combine.
        target_count: Target number of questions (default 30).

    Returns:
        A tuple of (merged_quiz, is_complete). If question count is less than target_count,
        is_complete will be False.
    """
    if not quizzes:
        empty = Quiz(
            course_code="UNKNOWN",
            lecture_no=0,
            variant="1",
            title="Empty Quiz",
            source_pdf="",
            prompt_version="1.0",
            questions=[],
        )
        return empty, False

    base = quizzes[0]
    deduped = _collect_unique_questions(quizzes)
    v_pfx = base.variant[:1] if base.variant else "1"

    reindexed = [
        Question(
            id=f"{base.course_code}-{base.lecture_no:02d}-Q{v_pfx}-{idx:03d}",
            question=orig.question,
            choices=orig.choices,
            answer_index=orig.answer_index,
            explanation=orig.explanation,
            source=orig.source,
            hint=orig.hint,
        )
        for idx, orig in enumerate(deduped[:target_count], start=1)
    ]

    is_complete = len(reindexed) >= target_count
    merged = Quiz(
        course_code=base.course_code,
        lecture_no=base.lecture_no,
        variant=base.variant,
        title=base.title,
        source_pdf=base.source_pdf,
        prompt_version=base.prompt_version,
        questions=reindexed,
    )
    return merged, is_complete


def to_exam_markdown(quiz: Quiz) -> str:
    """Format Quiz as a student practice paper (題目卷.md) without answers or rationales.

    Args:
        quiz: Domain Quiz entity.

    Returns:
        Markdown string suitable for student self-testing.
    """
    lines: list[str] = [
        f"# {quiz.title} — 題目卷",
        "",
        f"- **課程代碼**: `{quiz.course_code}`",
        f"- **講次編號**: 第 {quiz.lecture_no:02d} 講",
        f"- **測驗版本**: {quiz.variant}",
        f"- **題數**: 共 {len(quiz.questions)} 題",
        f"- **出處講義**: `{quiz.source_pdf}`",
        "",
        "> 💡 **作答說明**：本試卷為自主測驗練習卷，請選出最適當選項。"
        " 完成後可對照《答案與詳解卷》核對成績與深度解析。",
        "",
        "---",
        "",
    ]

    for idx, q in enumerate(quiz.questions, start=1):
        lines.append(f"### 第 {idx} 題")
        lines.append("")
        lines.append(q.question)
        lines.append("")
        for opt_idx, choice in enumerate(q.choices):
            letter = CHOICE_LABELS[opt_idx] if opt_idx < len(CHOICE_LABELS) else f"({opt_idx + 1})"
            lines.append(f"- **({letter})** {choice.text}")
        lines.append("")

    return "\n".join(lines)


def _format_single_answer(idx: int, q: Question) -> list[str]:
    """Format a single question with answers and option rationales for answer key.

    Args:
        idx: 1-based question number.
        q: Question domain entity.

    Returns:
        List of formatted markdown lines.
    """
    correct_letter = CHOICE_LABELS[q.answer_index] if q.answer_index < len(CHOICE_LABELS) else "未知"
    correct_text = q.choices[q.answer_index].text if 0 <= q.answer_index < len(q.choices) else ""

    lines: list[str] = [f"### 第 {idx} 題", "", q.question, ""]
    for opt_idx, choice in enumerate(q.choices):
        letter = CHOICE_LABELS[opt_idx] if opt_idx < len(CHOICE_LABELS) else f"({opt_idx + 1})"
        mark = " ✅" if opt_idx == q.answer_index else ""
        lines.append(f"- **({letter})** {choice.text}{mark}")
    lines.append("")
    lines.append(f"- **【正確解答】**: **({correct_letter})** {correct_text}")
    lines.append("")
    lines.append("- **【各選項詳解】**:")
    for opt_idx, choice in enumerate(q.choices):
        letter = CHOICE_LABELS[opt_idx] if opt_idx < len(CHOICE_LABELS) else f"({opt_idx + 1})"
        prefix = "正解說明" if opt_idx == q.answer_index else "錯誤分析"
        lines.append(f"  - **({letter})** [{prefix}]: {choice.rationale or '詳見教材章節說明'}")
    if q.hint:
        lines.append("")
        lines.append(f"- **【解題思路與提示】**: {q.hint}")
    lines.extend(["", "---", ""])
    return lines


def to_answer_markdown(quiz: Quiz) -> str:
    """Format Quiz as a teacher/study answer key (答案卷.md) with answers and rationales.

    Args:
        quiz: Domain Quiz entity.

    Returns:
        Markdown string containing answer keys, option rationales, and hints.
    """
    lines: list[str] = [
        f"# {quiz.title} — 答案與詳解卷",
        "",
        f"- **課程代碼**: `{quiz.course_code}`",
        f"- **講次編號**: 第 {quiz.lecture_no:02d} 講",
        f"- **測驗版本**: {quiz.variant}",
        f"- **題數**: 共 {len(quiz.questions)} 題",
        f"- **出處講義**: `{quiz.source_pdf}`",
        "",
        "> 📖 **學習指引**：檢視每題解析，特別注意錯誤選項之盲點剖析與思考指引。",
        "",
        "---",
        "",
    ]

    for idx, q in enumerate(quiz.questions, start=1):
        lines.extend(_format_single_answer(idx, q))

    return "\n".join(lines)


def _serialize_question(q: Question) -> dict[str, Any]:
    """Serialize a single Question entity into a dictionary.

    Args:
        q: Domain Question entity.

    Returns:
        Dictionary representation.
    """
    return {
        "id": q.id,
        "question": q.question,
        "choices": [
            {
                "text": c.text,
                "is_correct": c.is_correct,
                "rationale": c.rationale,
            }
            for c in q.choices
        ],
        "answer_index": q.answer_index,
        "explanation": q.explanation,
        "hint": q.hint,
        "source": q.source,
    }


def to_json(quiz: Quiz) -> str:
    """Serialize domain Quiz entity into standard JSON format.

    Args:
        quiz: Domain Quiz entity.

    Returns:
        JSON string representation.
    """
    quiz_dict = {
        "course_code": quiz.course_code,
        "lecture_no": quiz.lecture_no,
        "variant": quiz.variant,
        "title": quiz.title,
        "source_pdf": quiz.source_pdf,
        "prompt_version": quiz.prompt_version,
        "questions_count": len(quiz.questions),
        "questions": [_serialize_question(q) for q in quiz.questions],
    }
    return json.dumps(quiz_dict, ensure_ascii=False, indent=2)


def _get_interactive_quiz_css() -> str:
    """Return inline CSS rules for interactive quiz document.

    Returns:
        CSS stylesheet string.
    """
    css_lines = [
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
        "background:#0f172a;color:#f8fafc;margin:0;padding:24px;}",
        ".container{max-width:800px;margin:0 auto;}",
        ".header{border-bottom:1px solid #334155;padding-bottom:16px;margin-bottom:24px;}",
        ".q-card{background:#1e293b;border-radius:8px;padding:20px;margin-bottom:20px;",
        "border:1px solid #334155;}",
        ".q-title{font-size:1.1rem;font-weight:600;margin-bottom:14px;line-height:1.5;}",
        ".choice{display:block;background:#0f172a;border:1px solid #475569;padding:10px 14px;"
        "margin-bottom:8px;border-radius:6px;cursor:pointer;transition:all 0.2s;}",
        ".choice:hover{border-color:#38bdf8;}",
        ".choice.selected{border-color:#38bdf8;background:#1e3a8a;}",
        ".choice.correct{border-color:#22c55e;background:#14532d;font-weight:600;}",
        ".choice.wrong{border-color:#ef4444;background:#7f1d1d;}",
        ".explanation{display:none;margin-top:14px;padding:12px;background:#0f172a;",
        "border-left:4px solid #38bdf8;border-radius:4px;font-size:0.95rem;line-height:1.6;color:#cbd5e1;}",
        ".score-bar{position:sticky;bottom:20px;background:#1e293b;padding:14px 20px;border-radius:8px;",
        "border:1px solid #38bdf8;display:flex;justify-content:space-between;align-items:center;}",
        ".btn{background:#2563eb;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;",
        "font-weight:600;}",
        "</style>",
    ]
    return "".join(css_lines)


def _get_interactive_quiz_js(quiz_json: str) -> str:
    """Return inline JavaScript for interactive scoring and answer revelation.

    Args:
        quiz_json: JSON-encoded quiz questions and metadata.

    Returns:
        JavaScript script tag string.
    """
    js_lines = [
        f"<script>const data={quiz_json};const answers={{}};",
        "function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}",
        "const container=document.getElementById('quiz-container');",
        "data.questions.forEach((q,qIdx)=>{const card=document.createElement('div');card.className='q-card';",
        "let h=`<div class='q-title'>${qIdx+1}. ${esc(q.question)}</div>`;",
        "q.choices.forEach((c,cIdx)=>{const l=String.fromCharCode(65+cIdx);",
        "h+=`<div class='choice' id='c-${qIdx}-${cIdx}' onclick='selectChoice(${qIdx},${cIdx})'>`",
        "+ `${l}. ${esc(c)}</div>`;});",
        "h+=`<div class='explanation' id='exp-${qIdx}'><p style='color:#4ade80;margin:0 0 6px 0;'>`",
        "+ `<strong>正確解答：${String.fromCharCode(65+q.answer_index)}</strong></p>`",
        "+ `<p style='margin:0;'>${esc(q.explanation)}</p></div>`;",
        "card.innerHTML=h;container.appendChild(card);});",
        "function selectChoice(qIdx,cIdx){answers[qIdx]=cIdx;const q=data.questions[qIdx];",
        "for(let i=0;i<q.choices.length;i++){const el=document.getElementById(`c-${qIdx}-${i}`);",
        "el.classList.remove('selected','correct','wrong');if(i===cIdx)el.classList.add('selected');}",
        "updateScoreBar();}",
        "function updateScoreBar(){const len=Object.keys(answers).length;",
        "document.getElementById('score-text').textContent=`已作答: ${len} / ${data.questions.length}`;}",
        "function submitAll(){let correct=0;data.questions.forEach((q,qIdx)=>{const u=answers[qIdx];",
        "document.getElementById(`exp-${qIdx}`).style.display='block';",
        "for(let i=0;i<q.choices.length;i++){const el=document.getElementById(`c-${qIdx}-${i}`);",
        "if(i===q.answer_index){el.classList.add('correct');}else if(i===u){el.classList.add('wrong');}}",
        "if(u===q.answer_index)correct++;});",
        "const resHtml=`<strong>測驗得分：${correct} / ${data.questions.length}</strong>`;",
        "document.getElementById('score-text').innerHTML=resHtml;",
        "window.scrollTo({top:0,behavior:'smooth'});}</script>",
    ]
    return "".join(js_lines)


def to_interactive_html(quiz: Quiz) -> str:
    """Generate self-contained interactive quiz web application.

    Args:
        quiz: Domain Quiz entity.

    Returns:
        Full HTML string with interactive testing capabilities.
    """
    quiz_data = {
        "title": quiz.title,
        "questions": [
            {
                "id": q.id,
                "question": q.question,
                "choices": [c.text for c in q.choices],
                "answer_index": q.answer_index,
                "explanation": q.explanation,
            }
            for q in quiz.questions
        ],
    }
    quiz_json = json.dumps(quiz_data, ensure_ascii=False)
    css = _get_interactive_quiz_css()
    js = _get_interactive_quiz_js(quiz_json)
    safe_title = html.escape(quiz.title)
    html_lines = [
        "<!DOCTYPE html>",
        f'<html lang="zh-TW"><head><meta charset="utf-8"><title>{safe_title} — 互動測驗</title>',
        f'<meta name="viewport" content="width=device-width, initial-scale=1">{css}</head>',
        '<body><div class="container"><div class="header">',
        f"<h1>{safe_title}</h1>",
        f'<p style="color:#94a3b8;">共 {len(quiz.questions)} 題・即時互動答題與學術解析</p></div>',
        '<div id="quiz-container"></div><div class="score-bar">',
        f'<div id="score-text">已作答: 0 / {len(quiz.questions)}</div>',
        '<button class="btn" onclick="submitAll()">交卷評分 / 顯示全部解析</button></div></div>',
        f"{js}</body></html>",
    ]
    return "".join(html_lines)


def to_pdf(
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
    return render_quiz_pdf(quiz, output_path, is_answer_key=is_answer_key, title=title)
