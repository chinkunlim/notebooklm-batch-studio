"""Cross-term learning record aggregation and Markdown/PDF export (Refs: SPEC-014 Task 12)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.course_identity import TERM_PATTERN, make_course_code, parse_course_folder
from notebooklm_batch_studio.domain.memory_model import lecture_memory
from notebooklm_batch_studio.domain.models import Course, JobStatus
from notebooklm_batch_studio.domain.qa_notes import QANoteRepositoryProtocol
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    QueueRepositoryProtocol,
    StudyRepositoryProtocol,
)
from notebooklm_batch_studio.domain.study_layout import CategoryRole
from notebooklm_batch_studio.services.converters.note_pdf_renderer import render_markdown_to_pdf
from notebooklm_batch_studio.services.literature.protocols import LiteratureRepoProtocol
from notebooklm_batch_studio.services.notes.state_manager import _safe_key as safe_note_state_key

logger = logging.getLogger(__name__)

_STATS_ZERO: dict[str, int | float] = {
    "lectures": 0,
    "artifacts_done": 0,
    "quiz_attempts": 0,
    "quiz_best_score": 0,
    "mistakes_open": 0,
    "qa_notes": 0,
    "literature": 0,
    "notestudio_notes": 0,
    "study_days": 0,
    "study_minutes": 0,
    "memory_strength_avg": 0.0,
}


class LearningActivityRepoProtocol(Protocol):
    """Subset of LearningRepository needed for cross-term activity and memory estimates."""

    def activity_times(self, course_code: str) -> list[datetime]:
        """Return activity timestamps for a course.

        Args:
            course_code: Course code.

        Returns:
            List of timezone-aware timestamps.
        """
        ...

    def memory_signals(self, course_code: str) -> dict[int | None, dict[str, list[Any]]]:
        """Return per-lecture quiz and flashcard history for memory decay scoring.

        Args:
            course_code: Course code.

        Returns:
            Lecture-keyed dictionary containing `quizzes` and `cards` lists.
        """
        ...


@dataclass(frozen=True)
class CategoryFiles:
    """One category role and its discovered relative file paths for a course.

    Attributes:
        role: Semantic role value (e.g. `materials`, `handouts`, `notes`).
        files: Sorted relative file paths under the course folder (symlinks excluded).
    """

    role: str
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CourseRecordView:
    """Cross-term summary of one registered, archived, or unregistered course folder.

    Attributes:
        code: Course code (`<term>_<course_no>` or legacy code).
        name: Human-readable course name.
        term: Academic term label.
        status: `active`, `archived`, or `unregistered`.
        categories: Category file inventories without reading file contents.
        stats: Learning statistics mapping.
        artifacts: Done artifact entries (`lecture_no`, `artifact_type`, `rel_path`).
        study_dir: Absolute course folder (lets the web UI build file paths; Refs: SPEC-016).
    """

    code: str
    name: str
    term: str
    status: str
    categories: list[CategoryFiles]
    stats: dict[str, int | float]
    artifacts: list[dict[str, str]]
    study_dir: str = ""


@dataclass(frozen=True)
class TermRecordView:
    """Learning record grouping all courses and loose non-course entries for one academic term.

    Attributes:
        term: Academic term identifier (e.g. `115-1`).
        courses: Ordered course record views for this term.
        others: Non-course directory/file names directly under `study/<term>/`.
    """

    term: str
    courses: list[CourseRecordView]
    others: list[str]


@dataclass(frozen=True)
class RecordRepos:
    """Bundled read repositories consumed by `LearningRecordService`.

    Attributes:
        queue_repo: Queue repository for done artifacts.
        study_repo: Quiz attempt and mistake repository.
        learning_repo: Activity timestamps and memory signal repository.
        qa_repo: Saved Q&A notes repository.
        literature_repo: Literature reference repository.
    """

    queue_repo: QueueRepositoryProtocol
    study_repo: StudyRepositoryProtocol
    learning_repo: LearningActivityRepoProtocol
    qa_repo: QANoteRepositoryProtocol
    literature_repo: LiteratureRepoProtocol


def _estimate_study_minutes(times: list[datetime]) -> int:
    """Estimate active study minutes by clustering timestamps within 30-minute sessions.

    Args:
        times: Activity timestamps (any order).

    Returns:
        Total estimated minutes across clustered sessions.
    """
    if not times:
        return 0
    ordered = sorted(times)
    total = 0
    start = prev = ordered[0]
    for cur in ordered[1:]:
        if cur - prev > timedelta(minutes=30):
            total += max(5, int((prev - start).total_seconds() // 60) + 5)
            start = cur
        prev = cur
    return total + max(5, int((prev - start).total_seconds() // 60) + 5)


def _walk_dir_files(course_dir: Path, cat_dir: Path) -> list[str]:
    """Recursively list relative file paths under `cat_dir`, skipping hidden files and symlinks.

    Args:
        course_dir: Parent course study folder.
        cat_dir: Concrete category directory inside `course_dir`.

    Returns:
        Sorted list of POSIX paths relative to `course_dir`.
    """
    if course_dir.is_symlink() or cat_dir.is_symlink() or not cat_dir.is_dir():
        return []
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(cat_dir, topdown=True, followlinks=False):
        base = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and not (base / d).is_symlink())
        for fname in sorted(filenames):
            candidate = base / fname
            if fname.startswith(".") or candidate.is_symlink():
                continue
            found.append(candidate.relative_to(course_dir).as_posix())
    return found


def _short_course_label(course: CourseRecordView) -> str:
    """Return display course number/code prefix for Markdown section headings.

    Args:
        course: Rendered course record view.

    Returns:
        Short prefix such as `CP30000` when prefixed with `<term>_`, otherwise `course.code`.
    """
    prefix = f"{course.term}_"
    if course.term and course.code.startswith(prefix):
        return course.code.removeprefix(prefix)
    return course.code


class LearningRecordService:
    """Aggregate study folders, archived courses, stats, and exports across academic terms."""

    def __init__(self, config: AppConfig, course_repo: CourseRepositoryProtocol, repos: RecordRepos) -> None:
        """Bind configuration and read repositories.

        Args:
            config: Application configuration.
            course_repo: Course repository.
            repos: Bundled queue/study/learning/qa/literature repositories.
        """
        self.config = config
        self.course_repo = course_repo
        self.repos = repos

    def _collect_categories(self, course_dir: Path | None) -> tuple[list[CategoryFiles], int]:
        """Scan category files under `course_dir` without reading contents or following symlinks.

        Args:
            course_dir: Course study directory or None.

        Returns:
            `(categories_list, notestudio_md_count)` tuple.
        """
        if course_dir is None or course_dir.is_symlink() or not course_dir.is_dir():
            return [], 0
        categories: list[CategoryFiles] = []
        note_files = 0
        for role in CategoryRole:
            files: list[str] = []
            for cat_dir in self.config.study_layout.category_dirs(course_dir, role):
                found = _walk_dir_files(course_dir, cat_dir)
                files.extend(found)
                if role == CategoryRole.NOTES:
                    note_files += sum(1 for f in found if "/NoteStudio/" in f and f.endswith(".md"))
            if files:
                categories.append(CategoryFiles(role=role.value, files=sorted(dict.fromkeys(files))))
        return categories, note_files

    def _count_done_state_chapters(self, code: str) -> int:
        """Count completed NoteStudio chapters recorded in `notes_state_dir` for `code`.

        Args:
            code: Course code.

        Returns:
            Number of chapters marked `done` in persisted note state JSON.
        """
        path = self.config.notes_state_dir / f"{safe_note_state_key(code)}.json"
        if not path.is_file() or path.is_symlink():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        chapters = payload.get("chapters", {}) if isinstance(payload, dict) else {}
        return sum(1 for ch in chapters.values() if isinstance(ch, dict) and ch.get("status") == "done")

    def _compute_stats(
        self, course: Course, done_jobs: list[Any], ns_files: int, now: datetime
    ) -> dict[str, int | float]:
        """Compute cross-module learning stats for a registered course.

        Args:
            course: Registered `Course` entity.
            done_jobs: Completed artifact jobs.
            ns_files: Count of NoteStudio `.md` files found on disk.
            now: Reference UTC timestamp for memory retention calculations.

        Returns:
            Dictionary matching all 11 stats keys.
        """
        attempts = self.repos.study_repo.list_attempts(course.code)
        mistakes = self.repos.study_repo.list_mistakes(course.code, only_unresolved=True)
        times = self.repos.learning_repo.activity_times(course.code)
        signals = self.repos.learning_repo.memory_signals(course.code)
        strengths = [
            float(est["percent"])
            for sig in signals.values()
            if (est := lecture_memory(sig["quizzes"], sig["cards"], now)) is not None
        ]
        return {
            "lectures": len(course.lectures),
            "artifacts_done": len(done_jobs),
            "quiz_attempts": len(attempts),
            "quiz_best_score": max(
                (round(100 * a.score / a.total_questions) for a in attempts if a.total_questions > 0),
                default=0,
            ),
            "mistakes_open": len(mistakes),
            "qa_notes": len(self.repos.qa_repo.list_notes(course.code)),
            "literature": len(self.repos.literature_repo.list_items(course.code)),
            "notestudio_notes": max(ns_files, self._count_done_state_chapters(course.code)),
            "study_days": len({t.astimezone().date() for t in times}),
            "study_minutes": _estimate_study_minutes(times),
            "memory_strength_avg": round(sum(strengths) / len(strengths), 1) if strengths else 0.0,
        }

    def _build_registered_view(self, course: Course, term: str, now: datetime) -> CourseRecordView:
        """Build complete `CourseRecordView` (categories, stats, artifacts) for a registered course.

        Args:
            course: Registered `Course` entity.
            term: Resolved academic term string.
            now: Reference UTC timestamp for memory retention calculations.

        Returns:
            Populated `CourseRecordView`.
        """
        study_dir = Path(course.study_dir) if course.study_dir else None
        categories, ns_files = self._collect_categories(study_dir)
        done_jobs = self.repos.queue_repo.list_jobs(course_code=course.code, status=JobStatus.DONE)
        artifacts = [
            {
                "lecture_no": str(j.lecture_no or ""),
                "artifact_type": j.artifact_type.value,
                "rel_path": self._rel_artifact_path(j.output_file, study_dir),
            }
            for j in done_jobs
        ]
        stats = self._compute_stats(course, done_jobs, ns_files, now)
        return CourseRecordView(
            course.code,
            course.name,
            term,
            course.status.value,
            categories,
            stats,
            artifacts,
            course.study_dir,
        )

    def _rel_artifact_path(self, output_file: str | None, study_dir: Path | None) -> str:
        """Compute clean relative artifact path without leaving `DATA_DIR`.

        Args:
            output_file: Raw artifact output path from DB.
            study_dir: Course study directory if configured.

        Returns:
            Relative POSIX path under `study_dir` or `DATA_DIR`, else basename.
        """
        if not output_file:
            return ""
        p = Path(output_file)
        if study_dir is not None and p.is_relative_to(study_dir):
            return p.relative_to(study_dir).as_posix()
        if p.is_relative_to(self.config.data_dir):
            return p.relative_to(self.config.data_dir).as_posix()
        return p.name

    def _classify_unregistered_child(
        self,
        term_name: str,
        child: Path,
        existing_maps: tuple[dict[str, Course], dict[str, Course]],
        bucket: dict[str, Any],
    ) -> None:
        """Classify a single subdirectory/file inside `study/<term>/` if not already registered.

        Args:
            term_name: Academic term label.
            child: Candidate directory or file path.
            existing_maps: `(by_dir, by_code)` lookup dictionaries for registered courses.
            bucket: Mutable `{courses, others}` dictionary for `term_name`.
        """
        by_dir, by_code = existing_maps
        if child.name.startswith(".") or child.is_symlink():
            return
        if child.is_dir() and str(child.resolve()) in by_dir:
            return
        info = parse_course_folder(child.name) if child.is_dir() else None
        if info is None or not info.is_course:
            bucket["others"].append(child.name)
            return
        code = make_course_code(term_name, info.course_no)
        if code in by_code:
            return
        cats, ns = self._collect_categories(child)
        bucket["courses"].append(
            CourseRecordView(
                code,
                info.name,
                term_name,
                "unregistered",
                cats,
                {**_STATS_ZERO, "notestudio_notes": ns},
                [],
                str(child),
            )
        )

    def _collect_unregistered_and_others(
        self,
        by_dir: dict[str, Course],
        by_code: dict[str, Course],
        terms_map: dict[str, dict[str, Any]],
        term_filter: str | None = None,
    ) -> None:
        """Discover unregistered school course folders and term-level `others` under `study_root_dir`.

        Args:
            by_dir: Registered courses keyed by resolved `study_dir`.
            by_code: Registered courses keyed by code.
            terms_map: Mutable mapping `{term: {"courses": [...], "others": [...]}}`.
            term_filter: Optional term name to restrict scanning.
        """
        root = self.config.study_root_dir
        if not root.is_dir() or root.is_symlink():
            return
        for term_dir in sorted(root.iterdir(), key=lambda p: p.name):
            if term_dir.is_symlink() or not term_dir.is_dir() or not TERM_PATTERN.match(term_dir.name):
                continue
            if term_filter is not None and term_dir.name != term_filter:
                continue
            bucket = terms_map.setdefault(term_dir.name, {"courses": [], "others": []})
            for child in sorted(term_dir.iterdir(), key=lambda p: p.name):
                self._classify_unregistered_child(term_dir.name, child, (by_dir, by_code), bucket)

    def build(self, term: str | None = None) -> list[TermRecordView]:
        """Build sorted cross-term learning record views (including archived and unregistered courses).

        Args:
            term: Optional semester filter (e.g. `115-1`).

        Returns:
            Sorted list of `TermRecordView` objects.
        """
        now = datetime.now(UTC)
        courses = self.course_repo.list_courses()
        by_dir = {
            str(Path(c.study_dir).resolve()): c
            for c in courses
            if c.study_dir and not Path(c.study_dir).is_symlink()
        }
        by_code = {c.code: c for c in courses}
        terms_map: dict[str, dict[str, Any]] = {}
        for c in courses:
            c_term = c.term or (
                Path(c.study_dir).parent.name
                if c.study_dir and TERM_PATTERN.match(Path(c.study_dir).parent.name)
                else "未分學期"
            )
            if term is not None and c_term != term:
                continue
            bucket = terms_map.setdefault(c_term, {"courses": [], "others": []})
            bucket["courses"].append(self._build_registered_view(c, c_term, now))
        self._collect_unregistered_and_others(by_dir, by_code, terms_map, term_filter=term)
        keys = sorted((k for k in terms_map if term is None or k == term), key=lambda k: (k == "未分學期", k))
        return [
            TermRecordView(
                k, sorted(terms_map[k]["courses"], key=lambda x: x.code), sorted(terms_map[k]["others"])
            )
            for k in keys
        ]

    def export_markdown(self, term: str | None = None) -> str:
        """Render complete learning record views to Markdown.

        Args:
            term: Optional semester filter.

        Returns:
            Markdown report beginning with `# 學習紀錄`.
        """
        terms = self.build(term=term)
        lines: list[str] = ["# 學習紀錄", ""]
        for tv in terms:
            lines.extend([f"## {tv.term}", ""])
            for c in tv.courses:
                lines.append(f"### {_short_course_label(c)} {c.name}（{c.status}）")
                s = c.stats
                lines.append(
                    f"- 統計：講次 {s['lectures']}｜完成產出 {s['artifacts_done']}"
                    f"｜測驗 {s['quiz_attempts']} 次（最高 {s['quiz_best_score']}%）"
                    f"｜未解錯題 {s['mistakes_open']}｜問答筆記 {s['qa_notes']}"
                    f"｜文獻 {s['literature']}｜NoteStudio {s['notestudio_notes']}"
                    f"｜學習 {s['study_days']} 天 / 約 {s['study_minutes']} 分"
                    f"｜記憶強度 {s['memory_strength_avg']}%"
                )
                for cat in c.categories:
                    lines.append(f"- {cat.role}：{', '.join(cat.files)}")
                for art in c.artifacts:
                    lines.append(f"- 產出：L{art['lecture_no']} {art['artifact_type']} -> {art['rel_path']}")
                lines.append("")
            if tv.others:
                lines.append("### 其他項目")
                lines.extend([f"- {name}" for name in tv.others])
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def export_pdf(self, term: str | None, out: Path) -> Path:
        """Export the rendered learning record Markdown to an A4 PDF file.

        Args:
            term: Optional semester filter.
            out: Output PDF file path.

        Returns:
            Path to the generated PDF file.
        """
        md = self.export_markdown(term=term)
        return render_markdown_to_pdf("學習紀錄", md, out)
