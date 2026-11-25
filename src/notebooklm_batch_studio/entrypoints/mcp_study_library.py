"""MCP tool registrations for study library, filing, course lifecycle, and learning records (SPEC-014)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.adapters.db.course_identity_repo import CourseIdentityRepository
from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.study_layout import CategoryRole
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.services.adopt_outputs import AdoptOutputsService
from notebooklm_batch_studio.services.course_display_name import set_course_display_name as _set_display_name
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.filing import FilingService, FilingTarget
from notebooklm_batch_studio.services.learning_record import LearningRecordService, RecordRepos
from notebooklm_batch_studio.services.study_library import StudyLibraryService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def _dumps(payload: Any) -> str:
    """Serialize MCP response payload to a formatted UTF-8 JSON string.

    Args:
        payload: JSON-serializable response mapping or value.

    Returns:
        UTF-8 JSON string.
    """
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _record_service(cfg: AppConfig, db: Any) -> LearningRecordService:
    """Build `LearningRecordService` backed by the provided SQLAlchemy session.

    Args:
        cfg: Application configuration.
        db: Active SQLAlchemy session.

    Returns:
        Configured `LearningRecordService`.
    """
    repos = RecordRepos(
        queue_repo=QueueRepository(db),
        study_repo=StudyRepository(db),
        learning_repo=LearningRepository(db),
        qa_repo=QANoteRepository(db),
        literature_repo=LiteratureRepository(db),
    )
    return LearningRecordService(cfg, CourseRepository(db), repos)


def _parse_filing_target(target: str) -> FilingTarget:
    """Parse `CODE:ROLE[/SUB]` target specification into a `FilingTarget`.

    Args:
        target: Filing target string (`course_code:role` or `course_code:role/subfolder`).

    Returns:
        Parsed `FilingTarget`.
    """
    code, sep, rest = target.partition(":")
    if not sep or not code.strip() or not rest.strip():
        raise ValueError("target 格式必須為 `<課程代碼>:<角色>` 或 `<課程代碼>:<角色>/<子資料夾>`")
    role_str, _, sub = rest.partition("/")
    return FilingTarget(course_code=code.strip(), role=CategoryRole(role_str.strip()), subfolder=sub.strip())


def _lifecycle(cfg: AppConfig, db: Any) -> CourseLifecycleService:
    """Construct `CourseLifecycleService` bound to `cfg` and DB session `db`.

    Args:
        cfg: Application configuration.
        db: Active SQLAlchemy session.

    Returns:
        Configured `CourseLifecycleService`.
    """
    return CourseLifecycleService(
        CourseRepository(db), QueueRepository(db), CourseIdentityRepository(db), cfg
    )


def _register_layout_tool(mcp: MCPServer, cfg: AppConfig) -> None:
    """Register `get_study_layout` MCP tool.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
    """

    @mcp.tool()
    def get_study_layout() -> str:
        """Return configured study folder category names, aliases, and roles.

        Returns:
            JSON string describing category names, aliases, and roles.
        """
        layout = cfg.study_layout
        return _dumps(
            {
                "names": {r.value: layout.names[r] for r in CategoryRole},
                "aliases": {r.value: list(layout.aliases.get(r, ())) for r in CategoryRole},
                "roles": [r.value for r in CategoryRole],
            }
        )


def _register_scan_tools(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `scan_study_library` and `list_unfiled` MCP tools.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def scan_study_library() -> str:
        """Scan `DATA_DIR/study/` by academic term for course candidates and non-course entries.

        Returns:
            JSON string containing sorted `terms`.
        """
        with session_factory() as db:
            terms = StudyLibraryService(cfg, CourseRepository(db)).scan()
        return _dumps({"terms": [asdict(t) for t in terms]})

    @mcp.tool()
    def list_unfiled(kind: str | None = None) -> str:
        """List unfiled items waiting in `DATA_DIR/scratch/`.

        Args:
            kind: Optional scratch directory kind filter.

        Returns:
            JSON string containing `items` metadata list.
        """
        with session_factory() as db:
            items = FilingService(cfg, CourseRepository(db)).list_unfiled(kind)
        return _dumps({"items": items})


def _register_record_tools(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `get_learning_record` and `export_learning_record` MCP tools.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def get_learning_record(term: str | None = None) -> str:
        """Build cross-term learning record summary.

        Args:
            term: Optional academic term filter (e.g. `115-1`).

        Returns:
            JSON string containing `terms` record views.
        """
        with session_factory() as db:
            return _dumps({"terms": [asdict(t) for t in _record_service(cfg, db).build(term=term)]})

    @mcp.tool()
    def export_learning_record(term: str | None = None, format: str = "md") -> str:
        """Export cross-term learning record to Markdown (`md`) or a PDF file (`pdf`).

        Args:
            term: Optional academic term filter.
            format: Output format (`md` or `pdf`).

        Returns:
            JSON string with exported `markdown` or output PDF `path`.
        """
        with session_factory() as db:
            svc = _record_service(cfg, db)
            if format.strip().lower() != "pdf":
                return _dumps({"format": "md", "markdown": svc.export_markdown(term=term)})
            out = cfg.scratch_kind_dir("outputs") / f"learning-record-{term or 'all'}.pdf"
            return _dumps({"format": "pdf", "path": str(svc.export_pdf(term=term, out=out))})


def _register_past_courses_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `register_past_courses` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def register_past_courses(codes: list[str], archive: bool = True, confirm: bool = False) -> str:
        """Register scanned study-library course codes in record-only mode (requires confirm=True).

        Args:
            codes: Course codes to register.
            archive: Mark registered courses archived when True.
            confirm: Must be True to persist DB rows.

        Returns:
            JSON confirmation payload or registration results.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to register past courses.", codes=codes, archive=archive
            )
        with session_factory() as db:
            results = StudyLibraryService(cfg, CourseRepository(db)).register(codes, archive=archive)
        return _dumps({"confirmed": True, "results": results})


def _register_study_folder_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `register_study_folder` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def register_study_folder(term: str, folder: str, course_no: str, confirm: bool = False) -> str:
        """Register a non-standard folder under `study/<term>/` with an explicit course number.

        Args:
            term: Academic term string.
            folder: Subfolder basename under `study/<term>/`.
            course_no: Course number assigned to the folder.
            confirm: Must be True to persist DB row.

        Returns:
            JSON confirmation payload or registered course metadata.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to register folder.", term=term, folder=folder, course_no=course_no
            )
        with session_factory() as db:
            res = StudyLibraryService(cfg, CourseRepository(db)).register_folder(term, folder, course_no)
        return _dumps({"confirmed": True, **res})


def _register_file_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `file_item` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def file_item(path: str, target: str, confirm: bool = False) -> str:
        """Move a file into `<course_code>:<role>[/<subfolder>]` (requires confirm=True).

        Args:
            path: Existing file path inside `scratch/` or a registered course folder.
            target: Target specification `<course_code>:<role>[/<subfolder>]`.
            confirm: Must be True to move the file.

        Returns:
            JSON confirmation payload or destination path.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to move file into course category.", path=path, target=target
            )
        parsed = _parse_filing_target(target)
        with session_factory() as db:
            dest = FilingService(cfg, CourseRepository(db)).file(Path(path), parsed)
        return _dumps({"confirmed": True, "dest": str(dest)})


def _register_unfile_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `unfile_item` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def unfile_item(path: str, confirm: bool = False) -> str:
        """Move a course file back into `scratch/unarchived/` (requires confirm=True).

        Args:
            path: Existing file path inside a registered course directory.
            confirm: Must be True to move the file.

        Returns:
            JSON confirmation payload or destination path.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to move course file back to scratch.", path=path)
        with session_factory() as db:
            dest = FilingService(cfg, CourseRepository(db)).unfile(Path(path))
        return _dumps({"confirmed": True, "dest": str(dest)})


def _register_archive_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `set_course_archived` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def set_course_archived(code: str, archived: bool, confirm: bool = False) -> str:
        """Archive or restore a course without touching local study files (requires confirm=True).

        Args:
            code: Course identifier.
            archived: True to archive, False to restore to active.
            confirm: Must be True to modify course status.

        Returns:
            JSON confirmation payload or updated status dictionary.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to change course archive status.", code=code, archived=archived
            )
        with session_factory() as db:
            svc = _lifecycle(cfg, db)
            res = svc.archive(code) if archived else svc.restore(code)
        return _dumps({"confirmed": True, **res})


def _register_rename_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `rename_course_code` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def rename_course_code(code: str, new_code: str, dry_run: bool = True, confirm: bool = False) -> str:
        """Preview (`dry_run=True`) or apply transactional course-code rename (requires confirm=True).

        Args:
            code: Current course code.
            new_code: Replacement course code.
            dry_run: Preview counts without changing DB or files when True.
            confirm: Must be True to proceed.

        Returns:
            JSON confirmation payload or rename counts summary.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to run course-code rename.", code=code, new_code=new_code, dry_run=dry_run
            )
        with session_factory() as db:
            res = _lifecycle(cfg, db).rename(code, new_code, dry_run=dry_run)
        return _dumps({"confirmed": True, **res})


def _register_adopt_outputs_tool(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `adopt_existing_outputs` MCP tool with `confirm` guard.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def adopt_existing_outputs(code: str, dry_run: bool = True, confirm: bool = False) -> str:
        """Preview (`dry_run=True`) or adopt existing local NotebookLM files into `done` jobs.

        Args:
            code: Registered course identifier.
            dry_run: Preview matches without modifying DB when True.
            confirm: Must be True to proceed.

        Returns:
            JSON confirmation payload or adoption summary.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to run adopt_existing_outputs.", code=code, dry_run=dry_run
            )
        with session_factory() as db:
            res = AdoptOutputsService(cfg, CourseRepository(db), QueueRepository(db)).adopt_existing_outputs(
                code, dry_run=dry_run
            )
        return _dumps({"confirmed": True, **res})


def _register_display_name_tool(mcp: MCPServer, session_factory: Any) -> None:
    """Register `set_course_display_name` MCP tool with `confirm` guard (Refs: SPEC-016).

    Args:
        mcp: MCPServer instance.
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def set_course_display_name(code: str, name: str, confirm: bool = False) -> str:
        """Change only a course's display name; code, subject, folder and notebook stay unchanged.

        Args:
            code: Registered course identifier.
            name: New display name.
            confirm: Must be True to proceed.

        Returns:
            JSON confirmation payload or `{code, name}`.
        """
        if not confirm:
            return confirm_warning(
                "Pass confirm=True to rename the course display name.", code=code, name=name
            )
        with session_factory() as db:
            res = _set_display_name(CourseRepository(db), code, name)
        return _dumps({"confirmed": True, **res})


def register_study_library_tools(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register all Task 13+ SPEC-015 MCP tools on `mcp`.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """
    _register_layout_tool(mcp, cfg)
    _register_scan_tools(mcp, cfg, session_factory)
    _register_record_tools(mcp, cfg, session_factory)
    _register_past_courses_tool(mcp, cfg, session_factory)
    _register_study_folder_tool(mcp, cfg, session_factory)
    _register_file_tool(mcp, cfg, session_factory)
    _register_unfile_tool(mcp, cfg, session_factory)
    _register_archive_tool(mcp, cfg, session_factory)
    _register_rename_tool(mcp, cfg, session_factory)
    _register_adopt_outputs_tool(mcp, cfg, session_factory)
    _register_display_name_tool(mcp, session_factory)
    logger.debug("Registered study library, filing, lifecycle, and adopt outputs MCP tools")
