"""MCP maintenance tools: list and prune database backups (moves to deleted/, never deletes; SPEC-017)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.services.backups import list_backups, prune_backups

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def register_maintenance_tools(mcp: MCPServer, cfg: AppConfig) -> None:
    """Register `list_backups` and `prune_backups` MCP tools.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
    """

    @mcp.tool(name="list_backups")
    def list_backups_tool() -> str:
        """List database backups in `DATA_DIR/backups/`, newest first.

        Returns:
            JSON string with `backups` array.
        """
        return json.dumps({"backups": list_backups(cfg)}, ensure_ascii=False)

    @mcp.tool(name="prune_backups")
    def prune_backups_tool(keep: int = 5, dry_run: bool = True, confirm: bool = False) -> str:
        """Keep the newest `keep` backups and move older ones into `DATA_DIR/deleted/backups/`.

        Args:
            keep: Number of newest backups to keep (at least 1).
            dry_run: Only preview when True.
            confirm: Must be True to proceed.

        Returns:
            JSON confirmation payload or prune summary.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to prune backups.", keep=keep, dry_run=dry_run)
        try:
            result = prune_backups(cfg, keep=keep, dry_run=dry_run)
        except ValueError as exc:
            return json.dumps({"confirmed": True, "error": str(exc)}, ensure_ascii=False)
        return json.dumps({"confirmed": True, **result}, ensure_ascii=False)

    logger.debug("Registered maintenance MCP tools")
