"""Course summary reporter: generates summary.md and summary.html for completed packages.

Lists course metadata, lecture progress, links to Gemini Notebook web interface,
and all generated deliverable files (audio MP3, quizzes, flashcards, mind maps, mock exam).
"""

from __future__ import annotations

import logging
from pathlib import Path

from notebooklm_batch_studio.domain.models import Course, JobStatus, Lecture

logger = logging.getLogger(__name__)


def _render_status_badge(status_str: str) -> str:
    """Render an HTML status badge with appropriate styling class.

    Args:
        status_str: JobStatus value string (e.g. done, quota_wait).

    Returns:
        HTML span snippet.
    """
    if status_str == "done":
        return "<span class='badge done'>已完成</span>"
    if status_str == "quota_wait":
        return "<span class='badge quota'>額度等待</span>"
    if status_str == "running":
        return "<span class='badge running'>生成中</span>"
    if status_str == "needs_review":
        return "<span class='badge review'>待複核</span>"
    return "<span class='badge pending'>待處理</span>"


def _render_html_rows(
    lectures: list[Lecture],
    job_statuses: dict[tuple[int | None, str], JobStatus],
) -> str:
    """Render HTML table rows for lectures.

    Args:
        lectures: List of lecture entities.
        job_statuses: Mapping of (lecture_no, artifact_type) -> JobStatus.

    Returns:
        Concatenated HTML tr elements.
    """
    rows: list[str] = []
    for lec in lectures:
        audio_st = job_statuses.get((lec.no, "audio"), JobStatus.PENDING).value
        q1_st = job_statuses.get((lec.no, "quiz_1"), JobStatus.PENDING).value
        fc_st = job_statuses.get((lec.no, "flashcards"), JobStatus.PENDING).value
        mm_st = job_statuses.get((lec.no, "mind_map"), JobStatus.PENDING).value

        rows.append(
            f"<tr>"
            f"<td>第 {lec.no:02d} 講</td>"
            f"<td><strong>{lec.topic}</strong></td>"
            f"<td><code>{lec.filename}</code></td>"
            f"<td>{_render_status_badge(audio_st)}</td>"
            f"<td>{_render_status_badge(q1_st)}</td>"
            f"<td>{_render_status_badge(fc_st)}</td>"
            f"<td>{_render_status_badge(mm_st)}</td>"
            f"</tr>"
        )
    return "".join(rows)


def _render_markdown_rows(
    lectures: list[Lecture],
    job_statuses: dict[tuple[int | None, str], JobStatus],
) -> list[str]:
    """Render Markdown table rows for lectures.

    Args:
        lectures: List of lecture entities.
        job_statuses: Mapping of (lecture_no, artifact_type) -> JobStatus.

    Returns:
        List of Markdown table row strings.
    """
    lines: list[str] = []
    for lec in lectures:
        audio_st = job_statuses.get((lec.no, "audio"), JobStatus.PENDING).value
        q1_st = job_statuses.get((lec.no, "quiz_1"), JobStatus.PENDING).value
        fc_st = job_statuses.get((lec.no, "flashcards"), JobStatus.PENDING).value
        mm_st = job_statuses.get((lec.no, "mind_map"), JobStatus.PENDING).value

        audio_icon = "✅" if audio_st == "done" else ("⏳" if audio_st == "quota_wait" else "⚪")
        quiz_icon = "✅" if q1_st == "done" else "⚪"
        fc_icon = "✅" if fc_st == "done" else "⚪"
        mm_icon = "✅" if mm_st == "done" else "⚪"

        lines.append(
            f"| 第 {lec.no:02d} 講 | {lec.topic} | `{lec.filename}` | "
            f"{audio_icon} | {quiz_icon} | {fc_icon} | {mm_icon} |"
        )
    return lines


class CourseReporter:
    """Generates markdown and HTML progress summaries for a course package."""

    def __init__(self, output_root: Path) -> None:
        """Initialize the course summary reporter.

        Args:
            output_root: Root directory where course output packages reside.
        """
        self.output_root = output_root

    def generate_summary(
        self,
        course: Course,
        job_statuses: dict[tuple[int | None, str], JobStatus] | None = None,
    ) -> tuple[Path, Path]:
        """Generate summary.md and summary.html in the course output folder.

        Args:
            course: The domain Course entity.
            job_statuses: Optional mapping of (lecture_no, artifact_type) -> JobStatus.

        Returns:
            Tuple of (summary_md_path, summary_html_path).
        """
        course_dir = self.output_root / course.code
        course_dir.mkdir(parents=True, exist_ok=True)

        md_path = course_dir / "summary.md"
        html_path = course_dir / "summary.html"

        md_content = self.render_markdown(course, job_statuses or {})
        html_content = self.render_html(course, job_statuses or {})

        md_path.write_text(md_content, encoding="utf-8")
        html_path.write_text(html_content, encoding="utf-8")

        logger.info("Generated course summaries for %s: %s, %s", course.code, md_path.name, html_path.name)
        return md_path, html_path

    def render_markdown(
        self,
        course: Course,
        job_statuses: dict[tuple[int | None, str], JobStatus],
    ) -> str:
        """Render markdown summary text for a course.

        Args:
            course: Domain Course entity.
            job_statuses: Mapping of (lecture_no, artifact_type) -> JobStatus.

        Returns:
            Formatted Markdown string.
        """
        nb_link = (
            f"[開啟 Gemini Notebook 筆記本](https://notebook.google.com/notebook/{course.notebook_id})"
            if course.notebook_id
            else "尚未關聯 Gemini Notebook"
        )
        exam_str = f"預定考試日期：`{course.exam_date}`" if course.exam_date else "未設定考試日期"

        lines: list[str] = [
            f"# 課程總覽：[{course.code}] {course.name}",
            "",
            f"- **課程代號**: `{course.code}`",
            f"- **生成設定檔**: `{course.profile.value}`",
            f"- **目標語言**: `{course.language}`",
            f"- **{exam_str}**",
            f"- **雲端連結**: {nb_link}",
            f"- **講次總數**: 共 {len(course.lectures)} 講",
            "",
            "## 講次產出清單",
            "",
            "| 講次 | 主題 | 來源講義 | 音訊 | 測驗卷 (1~3) | 單字卡 | 心智圖 |",
            "|---|---|---|:---:|:---:|:---:|:---:|",
        ]

        lines.extend(_render_markdown_rows(course.lectures, job_statuses))

        mock_st = job_statuses.get((None, "course_mock_exam"), JobStatus.PENDING).value
        cmm_st = job_statuses.get((None, "course_mind_map"), JobStatus.PENDING).value

        lines.extend(
            [
                "",
                "## 全課程整合複習",
                "",
                f"- **全課程模擬考 (50 題)**: "
                f"{'✅ 已完成 (`_course_exam/`)' if mock_st == 'done' else '⚪ 待排程'}",
                f"- **全課程總心智圖**: "
                f"{'✅ 已完成 (`_course_mindmap/`)' if cmm_st == 'done' else '⚪ 待排程'}",
                "",
            ]
        )
        return "\n".join(lines)

    def render_html(
        self,
        course: Course,
        job_statuses: dict[tuple[int | None, str], JobStatus],
    ) -> str:
        """Render responsive HTML summary dashboard for a course.

        Args:
            course: Domain Course entity.
            job_statuses: Mapping of (lecture_no, artifact_type) -> JobStatus.

        Returns:
            HTML page string with inline styling.
        """
        nb_url = f"https://notebook.google.com/notebook/{course.notebook_id}" if course.notebook_id else "#"
        rows_html = _render_html_rows(course.lectures, job_statuses)

        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[{course.code}] {course.name} — 複習學習包總覽</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 30px; color: #2d3748; background: #f7fafc; }}
  .container {{ max-width: 1000px; margin: auto; background: white; padding: 30px; border-radius: 8px; }}
  h1 {{ color: #1a202c; border-bottom: 2px solid #edf2f7; padding-bottom: 12px; margin-top: 0; }}
  .meta {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 25px; }}
  .meta-item {{ background: #edf2f7; padding: 8px 14px; border-radius: 6px; font-size: 14px; }}
  .btn {{ display: inline-block; padding: 8px 16px; background: #3182ce; color: white; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
  th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
  th {{ background: #f8fafc; color: #4a5568; font-weight: 600; }}
  .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; }}
  .badge.done {{ background: #c6f6d5; color: #22543d; }}
  .badge.quota {{ background: #feebc8; color: #744210; }}
  .badge.running {{ background: #bee3f8; color: #2b6cb0; }}
  .badge.review {{ background: #fed7d7; color: #742a2a; }}
  .badge.pending {{ background: #edf2f7; color: #718096; }}
</style>
</head>
<body>
<div class="container">
  <h1>[{course.code}] {course.name}</h1>
  <div class="meta">
    <div class="meta-item">課程代碼：<strong>{course.code}</strong></div>
    <div class="meta-item">設定檔：<strong>{course.profile.value}</strong></div>
    <div class="meta-item">語言：<strong>{course.language}</strong></div>
    <div class="meta-item">講次數：<strong>{len(course.lectures)}</strong></div>
    <a href="{nb_url}" target="_blank" class="btn">開啟 Gemini Notebook 雲端筆記本 ↗</a>
  </div>

  <h2>講次複習包產出狀態</h2>
  <table>
    <thead>
      <tr>
        <th>講次</th>
        <th>主題</th>
        <th>講義檔案</th>
        <th>音訊 (Audio)</th>
        <th>測驗卷 (Quiz 1~3)</th>
        <th>單字卡 (Flashcards)</th>
        <th>心智圖 (Mind Map)</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>
</body>
</html>
"""
