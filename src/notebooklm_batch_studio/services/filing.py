"""Archive/unfile files safely between `DATA_DIR/scratch/` and course study categories."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from notebooklm_batch_studio.config.settings import SCRATCH_KINDS, AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots, is_within, validate_path_segment
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilingTarget:
    """Destination specification for filing an unarchived file into a course category.

    Attributes:
        course_code: Registered target course code (e.g. `115-1_CP30000`).
        role: Target study category role (`MATERIALS`, `HANDOUTS`, `NOTES`, `HOMEWORK`, `ASSIGNMENTS`).
        subfolder: Optional subfolder relative to the category directory (required for `NOTES`).
    """

    course_code: str
    role: CategoryRole
    subfolder: str = ""


def _unique_dest_path(dest_dir: Path, filename: str, src: Path) -> Path:
    """Resolve collision-safe destination path inside `dest_dir` appending `-2`, `-3`, etc.

    Args:
        dest_dir: Verified destination directory.
        filename: Desired filename.
        src: Resolved source file path (returns unchanged target if identical).

    Returns:
        Destination path that will not overwrite an existing different file.
    """
    candidate = dest_dir / filename
    if candidate.resolve() == src.resolve() or not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    idx = 2
    while True:
        numbered = dest_dir / f"{stem}-{idx}{suffix}"
        if not numbered.exists():
            return numbered
        idx += 1


class FilingService:
    """Move files cleanly between `scratch/<kind>/` and registered course category folders."""

    def __init__(self, config: AppConfig, course_repo: CourseRepositoryProtocol) -> None:
        """Initialize the filing service.

        Args:
            config: Application configuration providing `scratch_dir` and `study_layout`.
            course_repo: Persistence repository for resolving registered course directories.
        """
        self.config = config
        self.course_repo = course_repo

    def _course_roots(self) -> list[tuple[Course, Path]]:
        """Return `(course, root_dir)` pairs for all registered courses with valid local directories.

        Returns:
            List of registered courses and their resolved `study_dir` or `source_dir`.
        """
        pairs: list[tuple[Course, Path]] = []
        for course in self.course_repo.list_courses():
            raw_root = course.study_dir or course.source_dir
            if raw_root:
                pairs.append((course, Path(raw_root).resolve()))
        return pairs

    def list_unfiled(self, kind: str | None = None) -> list[dict[str, str]]:
        """List unarchived files under `DATA_DIR/scratch/` optionally filtered by scratch kind.

        Args:
            kind: Optional scratch kind (`literature`, `notes`, `outputs`, `uploads`, `unarchived`).

        Returns:
            Sorted list of file metadata dictionaries (`kind`, `name`, `path`, `relative_path`).
        """
        kinds = (kind,) if kind is not None else SCRATCH_KINDS
        items: list[dict[str, str]] = []
        for k in kinds:
            k_dir = self.config.scratch_kind_dir(k)
            if not k_dir.is_dir():
                continue
            for entry in sorted(k_dir.rglob("*"), key=lambda p: str(p).lower()):
                if entry.is_file() and not entry.name.startswith("."):
                    rel = str(entry.relative_to(k_dir)).replace("\\", "/")
                    items.append({"kind": k, "name": entry.name, "path": str(entry), "relative_path": rel})
        return items

    def _resolve_target_dir(self, target: FilingTarget) -> Path:
        """Resolve and validate the destination category/subfolder path for `target`.

        Args:
            target: Target course, category role, and optional subfolder.

        Returns:
            Resolved destination directory within the course directory.

        Raises:
            CourseNotFoundError: When `target.course_code` does not exist.
            ValueError: When targeting `NOTES` root without a subfolder or missing course root.
        """
        course = self.course_repo.get_course(target.course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {target.course_code}")
        raw_base = course.study_dir or course.source_dir
        if not raw_base:
            raise ValueError(f"Course {course.code} has no local directory configured")
        base = Path(raw_base).resolve()
        sub = (target.subfolder or "").strip().strip("/")
        if target.role == CategoryRole.NOTES and not sub:
            raise ValueError("03 Notes 角色必須指定子資料夾，不可覆寫根目錄個人隨筆")
        dest_dir = self.config.study_layout.primary_dir(base, target.role)
        if sub:
            for part in Path(sub).parts:
                dest_dir = dest_dir / validate_path_segment(part, "subfolder")
        ensure_within_roots(dest_dir, [base], "target category directory")
        return dest_dir

    def file(self, path: Path, target: FilingTarget) -> Path:
        """Move a file from `scratch/` or a registered course directory into a course category.

        Args:
            path: Existing source file path inside `scratch_dir` or a registered course folder.
            target: Destination course code, category role, and optional subfolder.

        Returns:
            Destination path after moving (adds `-2`, `-3`, ... suffix on collision).

        Raises:
            FileNotFoundError: When `path` does not point to an existing file.
            PathSafetyError: When `path` lies outside `scratch_dir` and registered courses.
        """
        src = Path(path).resolve()
        allowed_roots = [self.config.scratch_dir.resolve(), *(root for _, root in self._course_roots())]
        ensure_within_roots(src, allowed_roots, "source file")
        if not src.is_file():
            raise FileNotFoundError(f"Source file not found: {src}")

        dest_dir = self._resolve_target_dir(target)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _unique_dest_path(dest_dir, src.name, src)
        if src != dest.resolve():
            shutil.move(str(src), str(dest))
        logger.info("Filed %s -> %s", src.name, dest)
        return dest

    def unfile(self, path: Path, dest_dir: Path | None = None) -> Path:
        """Move a file out of a registered course folder back to `scratch/unarchived/<code>/`.

        Args:
            path: Existing file inside a registered course directory.
            dest_dir: Optional explicit folder inside `scratch_dir` (defaults to `unarchived/<code>`).

        Returns:
            New file path inside `DATA_DIR/scratch/`.

        Raises:
            FileNotFoundError: When `path` is not an existing file.
            PathSafetyError: When `path` escapes registered courses or `dest_dir` escapes `scratch_dir`.
        """
        src = Path(path).resolve()
        roots = self._course_roots()
        ensure_within_roots(src, [root for _, root in roots], "course file")
        if not src.is_file():
            raise FileNotFoundError(f"Course file not found: {src}")

        matched = next((c for c, root in roots if is_within(src, root)), None)
        if matched is None:
            raise ValueError(f"File is not inside a registered course: {src}")
        target_dir = (dest_dir or (self.config.scratch_kind_dir("unarchived") / matched.code)).resolve()
        ensure_within_roots(target_dir, [self.config.scratch_dir.resolve()], "scratch directory")
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = _unique_dest_path(target_dir, src.name, src)
        if src != dest.resolve():
            shutil.move(str(src), str(dest))
        logger.info("Unfiled %s -> %s", src.name, dest)
        return dest
