"""MCP tools for Gemini Web authentication and session management (Refs: ISSUE-053)."""

from __future__ import annotations

import json
import logging

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.adapters.notebooklm.chrome_login import build_notebook_login_service
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.services.auth_status import sign_in_status
from notebooklm_batch_studio.services.notebook_login import LoginInProgressError
from notebooklm_batch_studio.services.notes.gemini_auth_service import GeminiAuthService

logger = logging.getLogger(__name__)


def _confirm_prompt(message: str) -> str:
    """Return standard unconfirmed JSON warning asking the caller to pass `confirm=True`.

    Args:
        message: Instruction explaining the required confirmation.

    Returns:
        JSON string `{"confirmed": False, "warning": ...}`.
    """
    return json.dumps({"confirmed": False, "warning": message}, ensure_ascii=False)


def _register_status_and_retention_tools(mcp: MCPServer, auth: GeminiAuthService) -> None:
    """Register auth status and retention policy MCP tools on `mcp`.

    Args:
        mcp: MCPServer instance.
        auth: Configured `GeminiAuthService`.
    """

    @mcp.tool()
    def notes_gemini_auth_status(live_check: bool = False) -> str:
        """Check whether the `gemini_web` note generation profile is logged in.

        Args:
            live_check: When True, actively probe gemini.google.com using saved cookies.

        Returns:
            JSON string with `logged_in`, `updated_at`, `cookie_count`, and retention info.
        """
        return json.dumps(auth.check_auth_status(live_check=live_check), ensure_ascii=False, indent=2)

    @mcp.tool()
    def notes_set_gemini_retention(retention_days: int, confirm: bool = False) -> str:
        """Configure how many days local Gemini cookies are kept (requires confirm=True).

        Args:
            retention_days: Retention days (`0` keeps session until Google expires it).
            confirm: Must be True to update retention settings.

        Returns:
            JSON string with saved policy or a confirmation warning.
        """
        if not confirm:
            return _confirm_prompt("Pass confirm=True to save Gemini Web cookie retention days.")
        return json.dumps(auth.set_retention_days(retention_days), ensure_ascii=False, indent=2)


def _register_login_and_logout_tools(mcp: MCPServer, auth: GeminiAuthService) -> None:
    """Register interactive Chrome login and logout MCP tools on `mcp`.

    Args:
        mcp: MCPServer instance.
        auth: Configured `GeminiAuthService`.
    """

    @mcp.tool()
    def notes_gemini_login(timeout_seconds: int = 300, confirm: bool = False) -> str:
        """Open a real Chrome window for interactive Google/Gemini sign-in (requires confirm=True).

        Args:
            timeout_seconds: Maximum seconds to wait for user login completion.
            confirm: Must be True to launch Chrome on the desktop.

        Returns:
            JSON string with `success`, `logged_in`, and `message`, or a confirmation warning.
        """
        if not confirm:
            return _confirm_prompt("Pass confirm=True to launch Chrome for interactive Gemini login.")
        return json.dumps(
            auth.login_interactive(timeout_seconds=timeout_seconds), ensure_ascii=False, indent=2
        )

    @mcp.tool()
    def notes_gemini_logout(confirm: bool = False) -> str:
        """Clear saved Gemini Chrome profile and session cookies (requires confirm=True).

        Args:
            confirm: Must be True to delete local session credentials.

        Returns:
            JSON string with `success` and `logged_in`, or a confirmation warning.
        """
        if not confirm:
            return _confirm_prompt("Pass confirm=True to clear local Gemini Web session credentials.")
        return json.dumps(auth.logout(), ensure_ascii=False, indent=2)


def _register_sign_in_overview_tool(mcp: MCPServer, config: AppConfig, auth: GeminiAuthService) -> None:
    """Register `get_sign_in_status` overview tool covering all 3 browser/session profiles.

    Args:
        mcp: MCPServer instance.
        config: Application configuration.
        auth: Configured `GeminiAuthService`.
    """

    @mcp.tool()
    def get_sign_in_status() -> str:
        """Report readiness across NotebookLM, Gemini Web, and library profiles without tokens.

        Returns:
            JSON string with `sign_ins` list.
        """
        return json.dumps({"sign_ins": sign_in_status(config, auth)}, ensure_ascii=False, indent=2)


def _register_notebook_login_tool(mcp: MCPServer, config: AppConfig) -> None:
    """Register `notebooklm_login`: real-Chrome Gemini Notebook sign-in (Refs: SPEC-022).

    Args:
        mcp: MCPServer instance.
        config: Application configuration.
    """
    service = build_notebook_login_service(config)

    @mcp.tool()
    def notebooklm_login(timeout_seconds: int = 300, confirm: bool = False) -> str:
        """Open real Chrome so the user signs in to Gemini Notebook personally (requires confirm=True).

        Args:
            timeout_seconds: Longest wait for the user to finish signing in.
            confirm: Must be True to open Chrome on the desktop.

        Returns:
            JSON string with `status` and `message` (never cookies), or a confirmation warning.
        """
        if not confirm:
            return _confirm_prompt("Pass confirm=True to open Chrome for Gemini Notebook sign-in.")
        try:
            return json.dumps(service.login(timeout_seconds), ensure_ascii=False, indent=2)
        except LoginInProgressError as exc:
            return json.dumps({"status": "in_progress", "message": str(exc)}, ensure_ascii=False)


def register_gemini_auth_tools(
    mcp: MCPServer, auth: GeminiAuthService, config: AppConfig | None = None
) -> None:
    """Register all Gemini Web authentication MCP tools.

    Args:
        mcp: MCPServer instance.
        auth: Configured `GeminiAuthService`.
        config: Optional `AppConfig` to also expose three-profile sign-in overview.
    """
    _register_status_and_retention_tools(mcp, auth)
    _register_login_and_logout_tools(mcp, auth)
    if config is not None:
        _register_sign_in_overview_tool(mcp, config, auth)
        _register_notebook_login_tool(mcp, config)
    logger.debug("Registered Gemini Web auth MCP tools")
