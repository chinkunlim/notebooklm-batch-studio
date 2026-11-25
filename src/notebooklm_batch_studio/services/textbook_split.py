"""Split `01 Materials` textbooks into chapter PDFs; move chapters out of `02 Handouts` (SPEC-018)."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots, validate_path_segment
from notebooklm_batch_studio.domain.textbook_sections import (
    TEXTBOOK_MARKER,
    ChapterSection,
    OutlineEntry,
    PageRangeJob,
    find_chapter_sections,
)
from notebooklm_batch_studio.services.course_parser import _collect_unique_lectures

logger = logging.getLogger(__name__)


class TextbookPdfProtocol(Protocol):
    """PDF capabilities supplied by the adapter layer."""

    def read_outline(self, pdf: Path) -> tuple[list[OutlineEntry], int]:
        """Return bookmarks and page count.

        Args:
            pdf: Source PDF.

        Returns:
            `(entries, total_pages)`.
        """
        ...

    def write_pages(self, job: PageRangeJob) -> None:
        """Write a page range with chapter-local bookmarks.

        Args:
            job: Source, page range, destination and bookmarks.
        """
        ...


class TextbookRepoProtocol(Protocol):
    """Course persistence needed by the textbook service."""

    def get_course(self, code: str) -> Course | None:
        """Return a course or None.

        Args:
            code: Course code.

        Returns:
            Course or None.
        """
        ...

    def save_course(self, course: Course) -> None:
        """Persist a course and its lectures.

        Args:
            course: Course entity.
        """
        ...

    def update_lecture_location(self, code: str, lecture_no: int, category: str, relative_path: str) -> bool:
        """Point a lecture at a moved PDF.

        Args:
            code: Course code.
            lecture_no: Lecture number.
            category: New category folder.
            relative_path: New course-relative path.

        Returns:
            True when updated.
        """
        ...


def _chapter_bookmarks(entries: list[OutlineEntry], section: ChapterSection) -> list[OutlineEntry]:
    """Bookmarks inside a chapter, re-based to chapter pages with a valid nesting.

    Args:
        entries: Whole-book outline.
        section: Chapter range.

    Returns:
        Chapter-relative bookmarks (first level is 1, each step deeper by at most 1).
    """
    inside = [e for e in entries if section.start <= e.page <= section.end and e.title]
    if not inside:
        return []
    base = min(e.level for e in inside)
    out: list[OutlineEntry] = []
    prev = 1
    for idx, entry in enumerate(inside):
        level = 1 if idx == 0 else min(entry.level - base + 1, prev + 1)
        out.append(OutlineEntry(max(level, 1), entry.title, entry.page - section.start + 1))
        prev = max(level, 1)
    return out


def _write_marker(folder: Path, source: str, chapters: list[str]) -> None:
    """Create or extend the `.textbook.json` marker of a chapter folder.

    Args:
        folder: Chapter folder.
        source: Original textbook file name ('' when chapters were moved from 02 Handouts).
        chapters: Chapter file names now in the folder.
    """
    marker = folder / TEXTBOOK_MARKER
    data = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    names = sorted(set(data.get("chapters", [])) | set(chapters))
    payload = {"source": data.get("source") or source, "chapters": names}
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_pdf(path: Path) -> bool:
    """Tell whether `path` is a visible PDF file.

    Args:
        path: Candidate path.

    Returns:
        True for visible `.pdf` files.
    """
    return path.is_file() and not path.name.startswith(".") and path.suffix.lower() == ".pdf"


def _chapter_folder(pdf: Path) -> Path:
    """Pick the chapter folder a whole-book PDF splits into. Refs: ISSUE-072

    The book's own `<stem>/` folder when it exists; otherwise the course's only marked chapter folder
    (chapters moved from `02 Handouts` live under the book's real title, which rarely matches the PDF
    file name), so existing chapters are kept instead of duplicated as new lectures.

    Args:
        pdf: Textbook PDF in a materials folder.

    Returns:
        Chapter folder path (may not exist yet).
    """
    own = pdf.parent / pdf.stem
    if own.is_dir():
        return own
    marked = [d for d in pdf.parent.iterdir() if d.is_dir() and (d / TEXTBOOK_MARKER).is_file()]
    return marked[0] if len(marked) == 1 else own


def _textbook_row(course_dir: Path, pdf: Path) -> dict[str, Any]:
    """Describe one textbook PDF and its chapter folder.

    Args:
        course_dir: Course study directory.
        pdf: Textbook PDF in a materials folder.

    Returns:
        `{relative_path, chapters_folder, split}`.
    """
    out = _chapter_folder(pdf)
    return {
        "relative_path": pdf.relative_to(course_dir).as_posix(),
        "chapters_folder": out.relative_to(course_dir).as_posix(),
        "split": (out / TEXTBOOK_MARKER).is_file(),
    }


def _section_row(section: ChapterSection, status: str) -> dict[str, Any]:
    """Serialize one planned chapter.

    Args:
        section: Detected chapter.
        status: `create` or `exists`.

    Returns:
        `{number, title, start, end, pages, filename, status}`.
    """
    keys = ("number", "title", "start", "end", "pages", "filename")
    return {**{k: getattr(section, k) for k in keys}, "status": status}


def _move_row(no: int, src: Path, dest: Path, course_dir: Path) -> dict[str, Any]:
    """Describe one planned chapter move out of `02 Handouts`.

    Args:
        no: Lecture number.
        src: Current PDF path.
        dest: Destination chapter folder.
        course_dir: Course study directory.

    Returns:
        `{no, filename, from, to, status}`; status is `conflict` when the target already exists.
    """
    target = dest / src.name
    return {
        "no": no,
        "filename": src.name,
        "from": src.relative_to(course_dir).as_posix(),
        "to": target.relative_to(course_dir).as_posix(),
        "status": "conflict" if target.exists() else "move",
    }


class TextbookService:
    """List, split and relocate textbook chapter PDFs for one course without network calls."""

    def __init__(
        self, config: AppConfig, course_repo: TextbookRepoProtocol, pdf_tools: TextbookPdfProtocol
    ) -> None:
        """Bind configuration, repository and PDF adapter.

        Args:
            config: Application configuration (study layout).
            course_repo: Course repository.
            pdf_tools: PDF outline reader / page writer.
        """
        self.config = config
        self.course_repo = course_repo
        self.pdf = pdf_tools

    def _course(self, code: str) -> tuple[Course, Path]:
        """Load a course that has a study folder.

        Args:
            code: Course code.

        Returns:
            `(course, course_dir)`.

        Raises:
            CourseNotFoundError: Unknown course.
            ValueError: Course has no study folder.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"找不到課程：{code}")
        if not course.study_dir or not Path(course.study_dir).is_dir():
            raise ValueError(f"課程 {code} 沒有學習資料夾")
        return course, Path(course.study_dir).resolve()

    def _materials_target(self, course_dir: Path) -> Path:
        """Choose the materials folder to write into: plural name unless only a non-empty alias exists.

        Args:
            course_dir: Course study directory.

        Returns:
            Materials directory path (may not exist yet).
        """
        layout = self.config.study_layout
        primary = course_dir / layout.names[CategoryRole.MATERIALS]
        if primary.is_dir():
            return primary
        for alias in layout.category_dirs(course_dir, CategoryRole.MATERIALS):
            if any(not p.name.startswith(".") for p in alias.iterdir()):
                return alias
        return primary

    def list_textbooks(self, code: str) -> list[dict[str, Any]]:
        """List top-level PDFs in the course's materials folders.

        Args:
            code: Course code.

        Returns:
            `[{relative_path, chapters_folder, split}]`.
        """
        _, course_dir = self._course(code)
        mat_dirs = self.config.study_layout.category_dirs(course_dir, CategoryRole.MATERIALS)
        return [
            _textbook_row(course_dir, pdf) for d in mat_dirs for pdf in sorted(d.iterdir()) if _is_pdf(pdf)
        ]

    def pending_textbooks(self, codes: list[str]) -> list[dict[str, Any]]:
        """Find textbooks in `01 Materials` with chapters not split yet (Refs: SPEC-020, ISSUE-072).

        Args:
            codes: Course codes to inspect (courses without a study folder are skipped).

        Returns:
            `[{course_code, course_name, relative_path, chapters, existing, error}]`.
        """
        rows: list[dict[str, Any]] = []
        for code in codes:
            try:
                course, course_dir = self._course(code)
            except ValueError:
                continue
            for book in self.list_textbooks(code):
                row = self._pending_row(course_dir, book)
                pdf = course_dir / book["relative_path"]
                own_split = (pdf.parent / pdf.stem / TEXTBOOK_MARKER).is_file()
                # A marked folder may still miss chapters (only some were moved from 02 Handouts).
                if row["chapters"] > row["existing"] or (row["error"] and not own_split):
                    rows.append({"course_code": code, "course_name": course.name, **row})
        return rows

    def _pending_row(self, course_dir: Path, book: dict[str, Any]) -> dict[str, Any]:
        """Summarize one unsplit textbook: chapter count, chapters already on disk, or why it cannot split.

        Args:
            course_dir: Course study directory.
            book: Row from `list_textbooks`.

        Returns:
            `{relative_path, chapters, existing, error}`.
        """
        pdf = course_dir / book["relative_path"]
        try:
            _, plan = self._plan(pdf, _chapter_folder(pdf))
        except Exception as exc:  # unreadable PDF or no chapter bookmarks
            return {"relative_path": book["relative_path"], "chapters": 0, "existing": 0, "error": str(exc)}
        existing = sum(1 for _, status in plan if status == "exists")
        return {
            "relative_path": book["relative_path"],
            "chapters": len(plan),
            "existing": existing,
            "error": "",
        }

    def _resolve_textbook(self, course_dir: Path, relative_path: str) -> Path:
        """Validate that `relative_path` is a top-level PDF inside a materials folder.

        Args:
            course_dir: Course study directory.
            relative_path: Course-relative path.

        Returns:
            Absolute PDF path.

        Raises:
            ValueError: Path outside materials, not top-level, or not an existing PDF.
        """
        mat_dirs = [
            d.resolve() for d in self.config.study_layout.category_dirs(course_dir, CategoryRole.MATERIALS)
        ]
        pdf = ensure_within_roots(course_dir / relative_path, mat_dirs, "textbook")
        if pdf.parent not in mat_dirs or pdf.suffix.lower() != ".pdf" or not pdf.is_file():
            raise ValueError("只能切割 01 Materials 頂層的 PDF 課本")
        return pdf

    def _plan(self, pdf: Path, out_dir: Path) -> tuple[list[OutlineEntry], list[tuple[ChapterSection, str]]]:
        """Detect chapters and mark each as `create` or `exists`.

        Args:
            pdf: Textbook PDF.
            out_dir: Chapter output folder.

        Returns:
            `(outline, [(section, status)])`.

        Raises:
            ValueError: When the PDF has no chapter bookmarks.
        """
        entries, total = self.pdf.read_outline(pdf)
        sections = find_chapter_sections(entries, total)
        if not sections:
            raise ValueError(f"找不到章節書籤：{pdf.name}（沒有書籤的 PDF 目前無法自動切割）")
        existing = {p.name[:5] for p in out_dir.glob("Ch*.pdf")} if out_dir.is_dir() else set()
        return entries, [(s, "exists" if s.filename[:5] in existing else "create") for s in sections]

    def split_textbook(self, code: str, relative_path: str, dry_run: bool = True) -> dict[str, Any]:
        """Preview or write chapter PDFs into `01 Materials/<book>/`; existing chapters are skipped.

        Args:
            code: Course code.
            relative_path: Course-relative textbook path from `list_textbooks`.
            dry_run: Preview only when True.

        Returns:
            `{dry_run, source, output_dir, chapters: [{number, title, start, end, pages, filename, status}]}`.
        """
        course, course_dir = self._course(code)
        pdf = self._resolve_textbook(course_dir, relative_path)
        out_dir = _chapter_folder(pdf)
        entries, plan = self._plan(pdf, out_dir)
        if not dry_run:
            self._write_chapters(pdf, out_dir, entries, plan)
            self._sync_textbook_lectures(course, course_dir)
            logger.info("Split %s into %d chapters for %s", pdf.name, len(plan), code)
        rows = [_section_row(s, st) for s, st in plan]
        rel_out = out_dir.relative_to(course_dir).as_posix()
        return {"dry_run": dry_run, "source": relative_path, "output_dir": rel_out, "chapters": rows}

    def _write_chapters(
        self, pdf: Path, out_dir: Path, entries: list[OutlineEntry], plan: list[tuple[ChapterSection, str]]
    ) -> None:
        """Write the `create` chapters and refresh the folder marker.

        Args:
            pdf: Textbook PDF.
            out_dir: Chapter output folder.
            entries: Whole-book outline.
            plan: `(section, status)` pairs from `_plan`.
        """
        out_dir.mkdir(exist_ok=True)
        for section in (s for s, status in plan if status == "create"):
            bookmarks = _chapter_bookmarks(entries, section)
            self.pdf.write_pages(
                PageRangeJob(pdf, section.start, section.end, out_dir / section.filename, bookmarks)
            )
        _write_marker(out_dir, pdf.name, [p.name for p in out_dir.glob("Ch*.pdf")])

    def _sync_textbook_lectures(self, course: Course, course_dir: Path) -> None:
        """Refresh lectures from textbook chapters when `02 Handouts` has no PDFs (keeps upload state).

        Args:
            course: Registered course.
            course_dir: Course study directory.
        """
        layout = self.config.study_layout
        lectures = _collect_unique_lectures(course_dir, layout=layout)
        if lectures and all(lec.category in layout.all_names(CategoryRole.MATERIALS) for lec in lectures):
            self.course_repo.save_course(replace(course, lectures=lectures))
            logger.info("Synced %d textbook lectures for %s", len(lectures), course.code)

    def relocate_handouts(self, code: str, book_folder: str, dry_run: bool = True) -> dict[str, Any]:
        """Preview or move lecture PDFs from `02 Handouts` into `01 Materials/<book_folder>/`.

        Args:
            code: Course code.
            book_folder: Textbook folder name (single path segment).
            dry_run: Preview only when True.

        Returns:
            `{dry_run, book_folder, destination, moves: [{no, filename, from, to, status}]}`.

        Raises:
            ValueError: When a destination file already exists (apply only).
        """
        course, course_dir = self._course(code)
        folder = validate_path_segment(book_folder.strip(), "book_folder")
        dest = self._materials_target(course_dir) / folder
        handout_names = self.config.study_layout.all_names(CategoryRole.HANDOUTS)
        sources = [
            (lec.no, course_dir / (lec.relative_path or lec.filename))
            for lec in course.lectures
            if lec.category in handout_names
        ]
        moves = [_move_row(no, src, dest, course_dir) for no, src in sources if src.is_file()]
        if not dry_run and moves:
            self._apply_moves(code, course_dir, dest, moves)
        rel_dest = dest.relative_to(course_dir).as_posix()
        return {"dry_run": dry_run, "book_folder": folder, "destination": rel_dest, "moves": moves}

    def _apply_moves(self, code: str, course_dir: Path, dest: Path, moves: list[dict[str, Any]]) -> None:
        """Move files, update lecture rows, and write the marker.

        Args:
            code: Course code.
            course_dir: Course study directory.
            dest: Destination chapter folder.
            moves: Planned moves from `relocate_handouts`.

        Raises:
            ValueError: When any destination file already exists.
        """
        conflicts = [m["to"] for m in moves if m["status"] == "conflict"]
        if conflicts:
            raise ValueError(f"目的地已存在同名檔案，未搬移任何檔案：{', '.join(conflicts)}")
        dest.mkdir(parents=True, exist_ok=True)
        category = dest.parent.name
        for move in moves:
            shutil.move(str(course_dir / move["from"]), str(course_dir / move["to"]))
            self.course_repo.update_lecture_location(code, move["no"], category, move["to"])
        _write_marker(dest, "", [m["filename"] for m in moves])
        logger.info("Moved %d chapter PDFs of %s into %s", len(moves), code, dest)
