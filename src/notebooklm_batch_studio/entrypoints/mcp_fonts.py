"""MCP tools for downloaded Google Fonts (ADR-009); downloading and deleting require confirm=True."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.domain.exceptions import FontDownloadError
from notebooklm_batch_studio.services.font_service import FontService


def register_font_tools(mcp: MCPServer, fonts: FontService) -> None:
    """Register tools to list, download and delete fonts for the web page.

    Args:
        mcp: MCPServer instance.
        fonts: Font service.
    """

    @mcp.tool()
    def list_fonts() -> str:
        """List the Google Fonts downloaded for the web page (read-only).

        Returns:
            JSON string {"fonts": [...]}.
        """
        return json.dumps({"fonts": fonts.list_fonts()}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def install_google_font(family: str, confirm: bool = False) -> str:
        """Download a free Google Fonts family, e.g. "LXGW WenKai TC" (requires confirm=True).

        Args:
            family: Family name exactly as on fonts.google.com.
            confirm: Must be True to download.

        Returns:
            JSON string with the font's description, or a confirmation warning / error.
        """
        if not confirm:
            return json.dumps(
                {"confirm": "Call again with confirm=True to download this font."}, ensure_ascii=False
            )
        try:
            return json.dumps(fonts.install(family), ensure_ascii=False, indent=2)
        except (ValueError, FontDownloadError) as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def delete_font(slug: str, confirm: bool = False) -> str:
        """Delete a downloaded font (requires confirm=True).

        Args:
            slug: Font folder name from list_fonts.
            confirm: Must be True to delete.

        Returns:
            JSON string {"deleted": bool}, or a confirmation warning / error.
        """
        if not confirm:
            return json.dumps(
                {"confirm": "Call again with confirm=True to delete this font."}, ensure_ascii=False
            )
        try:
            return json.dumps({"deleted": fonts.delete(slug)}, ensure_ascii=False)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
