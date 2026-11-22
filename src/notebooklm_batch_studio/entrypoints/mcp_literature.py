"""MCP tools for literature fetching, APA 7 export, course import, and study migration (SPEC-012)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
from notebooklm_batch_studio.services.literature.notebook_service import LiteratureNotebookService
from notebooklm_batch_studio.services.study_migration import migrate_courses_to_study_hierarchy

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiteratureToolDeps:
    """Bundled dependencies for registering literature MCP tools.

    Attributes:
        service: Core `BatchStudioService`.
        config: Application configuration.
        runner: Shared `LiteratureJobRunner`.
        session_factory: SQLAlchemy session factory.
    """

    service: Any
    config: Any
    runner: LiteratureJobRunner
    session_factory: Any
    preferences: Any = None


def _make_manager(deps: LiteratureToolDeps, session: Any) -> LiteratureManager:
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
            mgr = _make_manager(deps, session)
            items = [mgr.serialize_item(item) for item in mgr.lit_repo.list_items(course_code=course_code)]
            return json.dumps({"items": items}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def export_literature_apa(course_code: str | None = None) -> str:
        """Export sorted APA 7 reference list for a course or all tracked items.

        Args:
            course_code: Optional course filter.

        Returns:
            JSON string with `count`, `plain`, and `html`.
        """
        with deps.session_factory() as session:
            return json.dumps(
                _make_manager(deps, session).export_apa_list(course_code), ensure_ascii=False, indent=2
            )


def _register_add_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `add_literature` MCP tool.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def add_literature(
        text: str,
        course_code: str | None = None,
        category: str = DEFAULT_LITERATURE_CATEGORY,
        subfolder: str = DEFAULT_LITERATURE_SUBFOLDER,
    ) -> str:
        """Add APA, DOI, or title entries to the literature fetch queue.

        Args:
            text: Newline-separated references.
            course_code: Optional linked course code.
            category: Study category (default `01 Material`).
            subfolder: Subfolder under category (default `Literature_Review`).

        Returns:
            JSON string with added count and keys.
        """
        with deps.session_factory() as session:
            added = _make_manager(deps, session).add_entries(
                text, course_code=course_code, category=category, subfolder=subfolder
            )
            return json.dumps({"added": len(added), "keys": [i.key for i in added]}, ensure_ascii=False)


def _register_process_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `process_literature` MCP tool.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def process_literature(
        interactive: bool = False, identify_only: bool = False, no_browser: bool = False
    ) -> str:
        """Start a background job to identify and download pending literature PDFs.

        Args:
            interactive: Launch visible Chrome for manual CAPTCHA/OpenAthens login.
            identify_only: Only resolve metadata and APA 7 without downloading PDFs.
            no_browser: Only try open-access HTTP sources.

        Returns:
            JSON string with started job metadata.
        """
        kind = "identify" if identify_only else ("interactive" if interactive else "download")
        try:
            job = deps.runner.start(
                kind=kind,
                opts=JobRunOptions(
                    interactive=interactive, identify_only=identify_only, no_browser=no_browser
                ),
            )
            return json.dumps({"job": job.__dict__}, ensure_ascii=False, indent=2)
        except AlreadyRunningError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def refresh_literature(key: str, interactive: bool = False) -> str:
        """Try to upgrade an author-copy PDF to the publisher's version of record.

        Args:
            key: Literature item key.
            interactive: Launch visible Chrome for manual CAPTCHA/OpenAthens login.

        Returns:
            JSON string with started job metadata.
        """
        try:
            job = deps.runner.start(
                kind="refresh",
                opts=JobRunOptions(keys=[key], refresh_keys=frozenset({key}), interactive=interactive),
            )
            return json.dumps({"job": job.__dict__}, ensure_ascii=False, indent=2)
        except AlreadyRunningError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_import_tool(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register `import_literature_to_course` MCP tool.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    def import_literature_to_course(key: str, course_code: str | None = None) -> str:
        """Import a downloaded literature PDF into its linked course folder and rescan lectures.

        Args:
            key: Literature item key.
            course_code: Optional course code override.

        Returns:
            JSON string with updated literature item.
        """
        with deps.session_factory() as session:
            mgr = _make_manager(deps, session)
            try:
                saved = mgr.import_to_course(key, course_code=course_code)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            course = mgr.course_repo.get_course(saved.course_code) if saved.course_code else None
            if course is not None:
                deps.service.register_course(course.source_dir, custom_code=course.code)
            return json.dumps({"item": mgr.serialize_item(saved)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def unarchive_literature(key: str) -> str:
        """Move an archived literature PDF back to the unarchived folder.

        Args:
            key: Literature item key.

        Returns:
            JSON string with updated literature item.
        """
        with deps.session_factory() as session:
            mgr = _make_manager(deps, session)
            try:
                saved = mgr.unarchive_item(key)
            except ValueError as exc:
                return json.dumps({"error": str(exc)}, ensure_ascii=False)
            return json.dumps({"item": mgr.serialize_item(saved)}, ensure_ascii=False, indent=2)


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
            return json.dumps(
                {"error": "Confirmation required: pass confirm=True to delete literature item."},
                ensure_ascii=False,
            )
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
            return json.dumps(
                {"error": "Confirmation required: pass confirm=True when dry_run=False."},
                ensure_ascii=False,
            )
        with deps.session_factory() as session:
            res = migrate_courses_to_study_hierarchy(
                StudyMigrationRepository(session), deps.config, dry_run=dry_run
            )
            return json.dumps(res, ensure_ascii=False, indent=2)


def _register_notebook_tools(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register Gemini Literature Notebook sync, search, and Literature Review MCP tools.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """

    @mcp.tool()
    async def sync_literature_notebook() -> str:
        """Create/reuse the Gemini Literature Notebook and upload downloaded PDFs.

        Returns:
            JSON string with notebook ID, URL, and upload count.
        """
        with deps.session_factory() as session:
            svc = LiteratureNotebookService(
                deps.service.notebooklm_client, _make_manager(deps, session), deps.preferences
            )
            return json.dumps(await svc.sync_pdfs(), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def query_literature_notebook(question: str) -> str:
        """Query the Gemini Literature Notebook to find relevant papers and insights.

        Args:
            question: Search or synthesis question.

        Returns:
            JSON string with `answer` and `references`.
        """
        with deps.session_factory() as session:
            svc = LiteratureNotebookService(
                deps.service.notebooklm_client, _make_manager(deps, session), deps.preferences
            )
            return json.dumps(await svc.query(question), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def generate_literature_review(key: str, force: bool = False) -> str:
        """Generate a Western-university-format Literature Review for one paper via Gemini Notebook.

        Args:
            key: Literature item key.
            force: Regenerate even if a review already exists.

        Returns:
            JSON string with `key` and `review_markdown`.
        """
        with deps.session_factory() as session:
            svc = LiteratureNotebookService(
                deps.service.notebooklm_client, _make_manager(deps, session), deps.preferences
            )
            updated = await svc.generate_review(key, force=force)
            return json.dumps(
                {"key": updated.key, "review_markdown": updated.review_markdown}, ensure_ascii=False, indent=2
            )


def register_literature_tools(mcp: MCPServer, deps: LiteratureToolDeps) -> None:
    """Register all literature and study-hierarchy MCP tools on `mcp`.

    Args:
        mcp: FastMCP server instance.
        deps: Bundled literature dependencies.
    """
    _register_list_tool(mcp, deps)
    _register_add_tool(mcp, deps)
    _register_process_tool(mcp, deps)
    _register_import_tool(mcp, deps)
    _register_delete_tool(mcp, deps)
    _register_migrate_tool(mcp, deps)
    if deps.preferences is not None:
        _register_notebook_tools(mcp, deps)
