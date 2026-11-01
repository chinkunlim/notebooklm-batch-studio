"""Naming rules for generated artifacts: Chinese labels, version suffixes, and the web naming guide.

One table describes what every artifact type means, how it is titled on NotebookLM and how its
files are named locally, so the runner, the API, MCP and the web page all explain the same rules.
Refs: ADR-005
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from notebooklm_batch_studio.domain.models import ArtifactType, get_artifact_english_title


@dataclass(frozen=True)
class ArtifactNaming:
    """How one artifact type is named and what it contains.

    Attributes:
        artifact_type: Artifact type value (e.g. 'quiz_1').
        label: Short Chinese name shown in the web app.
        meaning: What the artifact is for (difficulty, question count, scope).
        local_files: Main local file name(s) for version 1.
    """

    artifact_type: str
    label: str
    meaning: str
    local_files: str


_GUIDE: tuple[ArtifactNaming, ...] = (
    ArtifactNaming("audio", "語音摘要", "雙人對談 Deep Dive，繁體中文旁白", "<課程>_L01_audio.m4a"),
    ArtifactNaming(
        "quiz_1",
        "測驗 1・基礎",
        "確認記得重要名詞、定義與基本原理。難度 easy，預設 30 題（可在設定改）",
        "quiz_1_題目卷.pdf / quiz_1_答案卷.pdf",
    ),
    ArtifactNaming(
        "quiz_2",
        "測驗 2・理解",
        "把概念用在具體情境或例子裡。難度 medium，預設 30 題（可在設定改）",
        "quiz_2_題目卷.pdf / quiz_2_答案卷.pdf",
    ),
    ArtifactNaming(
        "quiz_3",
        "測驗 3・模擬考",
        "模擬正式考試：綜合多個概念、多步推理。難度 hard，預設 30 題（可在設定改）",
        "quiz_3_題目卷.pdf / quiz_3_答案卷.pdf",
    ),
    ArtifactNaming(
        "quiz_academic",
        "測驗・學術精研",
        "進階選用：研究所程度，比較理論、批判論證、複雜情境推理。難度 hard，預設 30 題（可在設定改）",
        "quiz_academic_題目卷.pdf",
    ),
    ArtifactNaming(
        "quiz_concept",
        "測驗・概念刷題",
        "進階選用：快速檢查觀念，名詞定義、易混淆概念、步驟順序。難度 medium，預設 30 題（可在設定改）",
        "quiz_concept_題目卷.pdf",
    ),
    ArtifactNaming("flashcards", "閃卡", "重點名詞與概念，可匯入 Anki", "flashcards.json / anki.csv"),
    ArtifactNaming("mind_map", "心智圖", "單講概念結構", "mindmap.opml / mindmap.md"),
    ArtifactNaming("infographic", "資訊圖表", "直式重點圖，另轉 A4 / iPad / MacBook 版本", "infographic.png"),
    ArtifactNaming("study_guide", "讀書指南", "重點、問答與名詞解釋", "study_guide.md"),
    ArtifactNaming("slide_deck", "投影片", "可下載 PDF 或 PPTX", "slide_deck.pdf"),
    ArtifactNaming("data_table", "資料表", "比較整理表", "data_table.csv"),
    ArtifactNaming("video", "影片摘要", "講解影片", "video.mp4"),
    ArtifactNaming("reports_briefing", "報告・簡報文件", "Briefing Doc", "<課程>_L01_briefing_doc.md"),
    ArtifactNaming(
        "reports_study_guide", "報告・讀書指南", "Study Guide 格式報告", "<課程>_L01_study_guide.md"
    ),
    ArtifactNaming("reports_blog_post", "報告・部落格文章", "Blog Post 格式", "<課程>_L01_blog_post.md"),
    ArtifactNaming(
        "reports_concept_explanation",
        "報告・概念解說",
        "逐一解釋核心概念：定義、例子、常見誤解",
        "<課程>_L01_concept_explanation.md",
    ),
    ArtifactNaming(
        "course_mock_exam",
        "全課程期末模擬考",
        "所有講次，預設 50 題（可在設定改）",
        "_course_synthesis/course_mock_exam_題目卷.pdf",
    ),
    ArtifactNaming(
        "course_quiz_academic",
        "全課程・學術精研考",
        "進階選用：全課程的學術精研版（研究所程度），預設 50 題（可在設定改）",
        "course_quiz_academic_題目卷.pdf",
    ),
    ArtifactNaming(
        "course_quiz_concept",
        "全課程・概念刷題考",
        "進階選用：全課程的概念刷題版（考前快速複習），預設 50 題（可在設定改）",
        "course_quiz_concept_題目卷.pdf",
    ),
    ArtifactNaming("course_mind_map", "全課程心智圖", "跨章節概念結構", "_course_synthesis/mindmap.opml"),
    ArtifactNaming("course_audio", "全課程語音摘要", "整門課統整對談", "<課程>_course_audio.m4a"),
    ArtifactNaming("course_study_guide", "全課程讀書指南", "整門課統整", "course_study_guide.md"),
    ArtifactNaming("course_infographic", "全課程資訊圖表", "整門課重點圖", "course_infographic.png"),
    ArtifactNaming("course_slide_deck", "全課程投影片", "整門課摘要投影片", "course_slide_deck.pdf"),
    ArtifactNaming("course_data_table", "全課程資料表", "整門課總表", "course_data_table.csv"),
    ArtifactNaming("course_video", "全課程影片", "整門課講解影片", "course_video.mp4"),
    ArtifactNaming(
        "course_reports_briefing",
        "全課程報告・簡報文件",
        "整門課 Briefing Doc",
        "<課程>_Course_briefing_doc.md",
    ),
    ArtifactNaming(
        "course_reports_study_guide",
        "全課程報告・讀書指南",
        "整門課 Study Guide",
        "<課程>_Course_study_guide.md",
    ),
    ArtifactNaming(
        "course_reports_blog_post", "全課程報告・部落格文章", "整門課 Blog Post", "<課程>_Course_blog_post.md"
    ),
    ArtifactNaming(
        "course_reports_concept_explanation",
        "全課程報告・概念解說",
        "跨章節核心概念與彼此關係",
        "<課程>_Course_concept_explanation.md",
    ),
)

NAMING_BY_TYPE: dict[str, ArtifactNaming] = {n.artifact_type: n for n in _GUIDE}

NAMING_RULES: tuple[str, ...] = (
    "NotebookLM 上的標題格式：[前綴] 英文名稱，例如 [Ch01] Quiz 1 - Fundamentals。",
    "前綴：PDF 檔名含 ch 或 chapter 時用 Ch01、Ch02…，否則用 L01、L02…；全課程產出用範圍，例如 Ch01-Ch06。",
    "本機檔案放在 output/courses/<課程>/<講次資料夾>/，全課程產出放在 _course_synthesis/。",
    "重新生成時保留舊版：NotebookLM 標題加「 (v2)」，本機檔名加「_v2」，例如 infographic_v2.png。",
    "quiz.json 與 答案卷.md（沒有前綴）是學習頁預設讀取的副本，內容是該講第一份完成的測驗。",
    "題數不足的測驗不會放進正式資料夾，會移到 needs_review/ 等你審查。",
)


def label_for(artifact_type: ArtifactType | str) -> str:
    """Return the Chinese label of an artifact type.

    Args:
        artifact_type: Artifact type enum or value.

    Returns:
        Chinese label, or the raw value when the type is not in the guide.
    """
    value = artifact_type.value if isinstance(artifact_type, ArtifactType) else str(artifact_type)
    naming = NAMING_BY_TYPE.get(value)
    return naming.label if naming else value


def versioned_title(title: str, version: int) -> str:
    """Add the regeneration suffix to a NotebookLM title.

    Args:
        title: Base title, e.g. '[Ch01] Infographic'.
        version: Job version (1 = first generation).

    Returns:
        The title unchanged for version 1, else e.g. '[Ch01] Infographic (v2)'.
    """
    return title if version <= 1 else f"{title} (v{version})"


def versioned_name(name: str, version: int) -> str:
    """Add the regeneration suffix to a local file name or file prefix.

    Args:
        name: File name ('infographic.png') or prefix without extension ('quiz_1').
        version: Job version (1 = first generation).

    Returns:
        The name unchanged for version 1, else 'infographic_v2.png' / 'quiz_1_v2'.
    """
    if version <= 1:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return f"{name}_v{version}"
    return f"{stem}_v{version}.{ext}"


def naming_guide() -> dict[str, Any]:
    """Build the naming guide shown in the web app and returned by HTTP / MCP.

    Returns:
        Dictionary with general `rules` and per-type `artifacts` (label, meaning, NotebookLM
        title example, local files).
    """
    artifacts = []
    for naming in _GUIDE:
        prefix = "Ch01-Ch06" if naming.artifact_type.startswith("course_") else "Ch01"
        row = asdict(naming)
        row["notebooklm_title"] = get_artifact_english_title(naming.artifact_type, prefix)
        artifacts.append(row)
    return {"rules": list(NAMING_RULES), "artifacts": artifacts}
