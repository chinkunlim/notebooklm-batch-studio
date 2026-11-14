"""Markdown formatting, YAML frontmatter, and 4-dimension hierarchical tag helpers (SPEC-011)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from notebooklm_batch_studio.domain.qa_notes import CourseQANote, MasteryStatus, NoteScene

SCENE_TAG_MAP = {
    NoteScene.QUIZ_EXPLAIN.value: "類型/測驗追問",
    NoteScene.STUDY_TAB.value: "類型/筆記庫探討",
    NoteScene.CHAT_DRAWER.value: "類型/自主探討",
}

MASTERY_TAG_MAP = {
    MasteryStatus.NEEDS_REVIEW.value: "掌握度/待加強",
    MasteryStatus.MASTERED.value: "掌握度/已搞懂",
}

SUMMARY_PROMPT = (
    "請將我們剛才的所有討論內容，依照以下 Markdown 規格整理成一份完整的精華學習筆記：\n"
    "1. 標題：以一級標題 (# ) 標註主題核心概念。\n"
    "2. 標籤：輸出格式相容的標籤列，包含：\n"
    "   - 課程歸屬：#課程/{course_code}/{lecture_slug} 及 #{lecture_slug}\n"
    "   - 來源場景：#{scene_tag}\n"
    "   - 掌握度：#掌握度/待加強\n"
    "   - 主題概念：請根據內容提煉 2~3 個主題標籤（如 #主題/學科/核心概念）\n"
    "3. 核心結論（TL;DR）：1~2 句話濃縮最重要觀念。\n"
    "4. 深度重點解析：條列說明、公式或代碼塊、關鍵辨析。\n"
    "5. 講義出處：引用的講義名稱與頁碼（若有）。\n"
    "6. 隨堂記憶卡：以 Q: 與 A: 格式提供 1~2 題最容易混淆的複習題。\n"
    "請直接以乾淨標準 Markdown 格式輸出，不要有多餘的問候語。"
)


def slugify_note_title(text: str) -> str:
    """Create a filesystem-safe slug from note title.

    Args:
        text: Raw note title.

    Returns:
        Safe ASCII/Unicode filename stem fragment.
    """
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip())
    return cleaned.strip("_")[:48] or "note"


def extract_tags_from_markdown(markdown_text: str) -> list[str]:
    """Extract hashtag tokens (including nested `#a/b/c` tags) from Markdown text.

    Args:
        markdown_text: Markdown content body.

    Returns:
        Deduplicated list of tag strings without leading `#`.
    """
    matches = re.findall(r"(?:^|\s)#([^\s#`]+)", markdown_text)
    seen: list[str] = []
    for raw in matches:
        tag = raw.strip(".,;:!?，。；：")
        if tag and not tag.isdigit() and tag not in seen:
            seen.append(tag)
    return seen


def extract_title_from_markdown(markdown_text: str, fallback: str = "問答精華筆記") -> str:
    """Extract the first H1 heading from Markdown text.

    Args:
        markdown_text: Markdown content body.
        fallback: Fallback title when no H1 heading exists.

    Returns:
        Extracted title string.
    """
    for line in markdown_text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()[:150] or fallback
    return fallback


def build_hierarchical_tags(
    course_code: str,
    lecture_no: int | None,
    scene: str,
    extra_tags: list[str] | None = None,
) -> list[str]:
    """Assemble standard 4-dimension hierarchical tags plus extracted topic tags.

    Args:
        course_code: Course identifier.
        lecture_no: Optional lecture sequence number.
        scene: Origin scene string.
        extra_tags: Additional user or AI tags.

    Returns:
        Ordered, deduplicated list of tags without leading `#`.
    """
    tags: list[str] = []
    if lecture_no is not None:
        lec_slug = f"L{lecture_no:02d}"
        tags.extend([f"課程/{course_code}/{lec_slug}", lec_slug])
    else:
        tags.append(f"課程/{course_code}")
    tags.append(SCENE_TAG_MAP.get(scene, "類型/自主探討"))
    tags.append(MASTERY_TAG_MAP[MasteryStatus.NEEDS_REVIEW.value])
    for item in extra_tags or []:
        clean = item.lstrip("#").strip()
        if clean and not clean.startswith("掌握度/") and clean not in tags:
            tags.append(clean)
    return tags


def sync_mastery_tag(tags: list[str], mastery_status: str) -> list[str]:
    """Replace any existing mastery tag with the tag matching `mastery_status`.

    Args:
        tags: Current tag list.
        mastery_status: Target mastery status (`needs_review` or `mastered`).

    Returns:
        Updated tag list.
    """
    filtered = [t for t in tags if not t.startswith("掌握度/")]
    target_tag = MASTERY_TAG_MAP.get(mastery_status, "掌握度/待加強")
    filtered.append(target_tag)
    return filtered


def render_note_file_text(note: CourseQANote) -> str:
    """Render a CourseQANote as Obsidian-compatible Markdown with YAML frontmatter.

    Args:
        note: CourseQANote entity.

    Returns:
        Complete Markdown document text.
    """
    tag_lines = "\n".join(f"  - {t}" for t in note.tags)
    inline_tags = " ".join(f"#{t}" for t in note.tags)
    ts = (note.updated_at or note.created_at or datetime.now(UTC)).isoformat()
    safe_title = note.title.replace('"', '\\"')
    frontmatter = (
        "---\n"
        f'id: "{note.id}"\n'
        f'title: "{safe_title}"\n'
        f'date: "{ts}"\n'
        f'course: "{note.course_code}"\n'
        f"lecture_no: {note.lecture_no if note.lecture_no is not None else 'null'}\n"
        f'type: "{note.source_scene}"\n'
        f'mastery: "{note.mastery_status}"\n'
        f"tags:\n{tag_lines}\n"
        "---\n\n"
    )
    body = note.content_markdown.strip()
    memo_block = f"\n\n## 個人備忘註記\n\n{note.personal_memo.strip()}\n" if note.personal_memo else "\n"
    return f"{frontmatter}> 標籤：{inline_tags}\n\n{body}{memo_block}"


def note_to_dict(note: CourseQANote) -> dict[str, Any]:
    """Serialize a CourseQANote entity to JSON-safe dictionary.

    Args:
        note: Domain CourseQANote object.

    Returns:
        Dictionary payload for HTTP/MCP responses.
    """
    return {
        "id": note.id,
        "course_code": note.course_code,
        "lecture_no": note.lecture_no,
        "title": note.title,
        "content_markdown": note.content_markdown,
        "personal_memo": note.personal_memo,
        "tags": list(note.tags),
        "source_scene": note.source_scene,
        "mastery_status": note.mastery_status,
        "is_uploaded_as_source": note.is_uploaded_as_source,
        "uploaded_source_id": note.uploaded_source_id,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
