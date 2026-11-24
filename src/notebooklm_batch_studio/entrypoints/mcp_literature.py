"""MCP tools for literature fetching, APA 7 export, course import, and study migration (SPEC-012).

Every tool that changes data, files, or the remote Literature Notebook requires `confirm=True`
(core rule 13; Refs: ISSUE-048), so an agent steered by injected text cannot act silently.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.study_migration_repo import StudyMigrationRepository
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError
from notebooklm_batch_studio.domain.study_hierarchy import (
    DEFAULT_LITERATURE_CATEGORY,
    DEFAULT_LITERATURE_SUBFOLDER,
)
from notebooklm_batch_studio.services.literature.jobs import JobRunOptions, LiteratureJobRunner
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.study_migration import migrate_courses_to_study_hierarchy

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


class LiteratureTarget(BaseModel):
    """Where newly added literature should be filed.

    Attributes:
        course_code: Optional linked course code.
        category: Study category (default `01 Material`).
        subfolder: Subfolder under the category (default `Literature_Review`).
    """

    course_code: str | None = None
    category: str = DEFAULT_LITERATURE_CATEGORY
    subfolder: str = DEFAULT_LITERATURE_SUBFOLDER


@dataclass(frozen=True)
class LiteratureToolDeps:
    """Bundled dependencies for registering literature MCP tools.

    Attributes:
        service: Core `BatchStudioService`.
        config: Application configuration.
        runner: Shared `LiteratureJobRunner`.
        session_factory: SQLAlchemy session factory.
        preferences: Optional preferences service (enables Literature Notebook tools).
    """

    service: Any
    config: Any
    runner: LiteratureJobRunner
    session_factory: Any
    preferences: Any = None


def make_manager(deps: LiteratureToolDeps, session: Any) -> LiteratureManager:
    """Construct a `LiteratureManager` bound to `session`.

    Args:
        deps: Bundled literature dependencies.
        session: Open SQLAlchemy session.

    Returns:
        Configured `LiteratureManager`.
    """
    return LiteratureManager(
        deps.config,
        LiteratureRepository(session),
        CourseRepository(session),
        AdapterLiteratureRuntime(deps.config),
    )


def confirm_required(action: str) -> str:
    """Build the standard JSON warning returned when a mutating tool is called without `confirm=True`.

    Args:
        action: Short description of what the call would do.

    Returns:
        JSON string with `confirmed: False` and a `warning` message.
    """
    logger.info("MCP literature tool refused without confirm: %s", action)
    return json.dumps(
        {"confirmed": False, "warning": f"Confirmation required: pass confirm=True to {action}."},
        ensure_ascii=False,
    )


def _to_json(payload: Any) -> str:
    """Serialize a tool result as pretty JSON.

    Args:
        payload: JSON-serializable value.

    Returns:
        JSON string.
    """
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _start_job(deps: LiteratureToolDeps, kind: str, opts: JobRunOptions) -> str:
    """Start a background literature job and report it as JSON.

    Args:
        deps: Bundled literature dependencies.
        kind: Job kind (`identify`, `download`, `interactive`, `refresh`).
        opts: Job options.

    Returns:
        JSON string with the job, or an error when another job is running.
    """
    try:
        job = deps.runner.start(kind=kind, opts=opts)
    except AlreadyRunningError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return _to_json({"job": job.__dict__})


def _register_list_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `list_literature` and `export_literature_apa` MCP tools.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def list_literature(course_code: str | None = None) -> str:
        """List tracked academic references and their download/import status.

        Args:
            course_code: Optional course filter.

        Returns:
            JSON string with tracked items.
        """
        with deps.session_factory() as session:
            mgr = make_manager(deps, session)
            items = [mgr.serialize_item(item) for item in mgr.lit_repo.list_items(course_code=course_code)]
            return _to_json({"items": items})

    @mcp.tool()
    def export_literature_apa(course_code: str | None = None) -> str:
        """Export sorted APA 7 reference list for a course or all tracked items.

        Args:
            course_code: Optional course filter.

        Returns:
            JSON string with `count`, `plain`, and `html`.
        """
        with deps.session_factory() as session:
            return _to_json(make_manager(deps, session).export_apa_list(course_code))


def _register_add_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `add_literature` MCP tool guarded by `confirm=True`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def add_literature(text: str, target: LiteratureTarget | None = None, confirm: bool = False) -> str:
        """Add APA, DOI, or title entries to the literature fetch queue (requires `confirm=True`).

        Args:
            text: Newline-separated references.
            target: Optional course / category / subfolder the PDFs should be filed under.
            confirm: Must be True to add the entries.

        Returns:
            JSON string with added count and keys.
        """
        if not confirm:
            return confirm_required("add literature entries")
        where = target or LiteratureTarget()
        with deps.session_factory() as session:
            added = make_manager(deps, session).add_entries(
                text, course_code=where.course_code, category=where.category, subfolder=where.subfolder
            )
            return json.dumps({"added": len(added), "keys": [i.key for i in added]}, ensure_ascii=False)


def _register_process_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `process_literature` MCP tool guarded by `confirm=True`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def process_literature(
        interactive: bool = False,
        identify_only: bool = False,
        no_browser: bool = False,
        confirm: bool = False,
    ) -> str:
        """Start a background job to identify and download pending literature PDFs (requires `confirm=True`).

        Args:
            interactive: Launch visible Chrome for manual CAPTCHA/OpenAthens login.
            identify_only: Only resolve metadata and APA 7 without downloading PDFs.
            no_browser: Only try open-access HTTP sources.
            confirm: Must be True to start the job.

        Returns:
            JSON string with started job metadata.
        """
        if not confirm:
            return confirm_required("start the literature download job")
        kind = "identify" if identify_only else ("interactive" if interactive else "download")
        opts = JobRunOptions(interactive=interactive, identify_only=identify_only, no_browser=no_browser)
        return _start_job(deps, kind, opts)


def _register_refresh_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `refresh_literature` MCP tool guarded by `confirm=True`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def refresh_literature(key: str, interactive: bool = False, confirm: bool = False) -> str:
        """Try to upgrade an author-copy PDF to the publisher's version of record (requires `confirm=True`).

        Args:
            key: Literature item key.
            interactive: Launch visible Chrome for manual CAPTCHA/OpenAthens login.
            confirm: Must be True to start the refresh job.

        Returns:
            JSON string with started job metadata.
        """
        if not confirm:
            return confirm_required("refresh the literature PDF")
        opts = JobRunOptions(keys=[key], refresh_keys=frozenset({key}), interactive=interactive)
        return _start_job(deps, "refresh", opts)


def _import_one(deps: LiteratureToolDeps, key: str, course_code: str | None) -> str:
    """Import one literature PDF into its course folder and rescan the course.

    Args:
        deps: Bundled literature dependencies.
        key: Literature item key.
        course_code: Optional course code override.

    Returns:
        JSON string with the updated item, or an error.
    """
    with deps.session_factory() as session:
        mgr = make_manager(deps, session)
        try:
            saved = mgr.import_to_course(key, course_code=course_code)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        course = mgr.course_repo.get_course(saved.course_code) if saved.course_code else None
        if course is not None:
            deps.service.register_course(course.source_dir, custom_code=course.code)
        return _to_json({"item": mgr.serialize_item(saved)})


def _register_import_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register the `import_literature_to_course` MCP tool.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def import_literature_to_course(key: str, course_code: str | None = None, confirm: bool = False) -> str:
        """Import a downloaded literature PDF into its linked course folder (requires `confirm=True`).

        Args:
            key: Literature item key.
            course_code: Optional course code override.
            confirm: Must be True to copy the PDF and rescan lectures.

        Returns:
            JSON string with updated literature item.
        """
        if not confirm:
            return confirm_required("import the PDF into the course folder")
        return _import_one(deps, key, course_code)


def _register_unarchive_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register the `unarchive_literature` MCP tool.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def unarchive_literature(key: str, confirm: bool = False) -> str:
        """Move an archived literature PDF back to the unarchived folder (requires `confirm=True`).

        Args:
            key: Literature item key.
            confirm: Must be True to move the file.

        Returns:
            JSON string with updated literature item.
        """
        if not confirm:
            return confirm_required("move the PDF back to the unarchived folder")
        with deps.session_factory() as session:
            mgr = make_manager(deps, session)
            try:
                saved = mgr.unarchive_item(key)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return _to_json({"item": mgr.serialize_item(saved)})


def _register_delete_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `delete_literature` MCP tool guarded by `confirm=True`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def delete_literature(key: str, confirm: bool = False) -> str:
        """Delete a literature item from the tracker list (requires `confirm=True`).

        Args:
            key: Literature item key.
            confirm: Must be True to confirm deletion.

        Returns:
            JSON string confirming deletion or requesting confirmation.
        """
        if not confirm:
            return confirm_required("delete literature item")
        with deps.session_factory() as session:
            deleted = LiteratureRepository(session).delete_item(key)
            return json.dumps({"deleted": deleted, "key": key}, ensure_ascii=False)


def _register_migrate_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `migrate_study_layout` MCP tool guarded by `confirm=True`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def migrate_study_layout(dry_run: bool = True, confirm: bool = False) -> str:
        """Migrate legacy course folders into `<STUDY_ROOT_DIR>/<term>/<subject>/<category>`.

        Args:
            dry_run: Preview planned moves without modifying disk or DB (default True).
            confirm: Must be True when `dry_run=False`.

        Returns:
            JSON string with migration plan or results.
        """
        if not dry_run and not confirm:
            return confirm_required("migrate when dry_run=False")
        with deps.session_factory() as session:
            res = migrate_courses_to_study_hierarchy(
                StudyMigrationRepository(session), deps.config, dry_run=dry_run
            )
            return _to_json(res)


def register_literature_tools(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register literature and study-hierarchy MCP tools (Notebook tools live in `mcp_literature_notebook`).

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """
    _register_list_tool(mcp, deps)
    _register_add_tool(mcp, deps)
    _register_process_tool(mcp, deps)
    _register_refresh_tool(mcp, deps)
    _register_import_tool(mcp, deps)
    _register_unarchive_tool(mcp, deps)
    _register_delete_tool(mcp, deps)
    _register_migrate_tool(mcp, deps)
