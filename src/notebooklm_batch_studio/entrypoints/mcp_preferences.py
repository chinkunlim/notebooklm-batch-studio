"""MCP tools for the web preferences recorded on this computer (ADR-009); changes require confirm=True."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.preferences_service import PreferencesService


def register_preferences_tools(mcp: MCPServer, prefs: PreferencesService) -> None:
    """Register tools to read, change and reset the web preferences.

    Args:
        mcp: MCPServer instance.
        prefs: Preferences service.
    """

    @mcp.tool()
    def get_ui_preferences() -> str:
        """Read every remembered web preference (palette, layout, avatar, fonts…; read-only).

        Returns:
            JSON string {"values": {key: value}}.
        """
        return json.dumps({"values": prefs.get_all()}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def set_ui_preferences(values: dict[str, str | None], confirm: bool = False) -> str:
        """Change web preferences, e.g. {"palette": "sage"}; null deletes (requires confirm=True).

        Args:
            values: Key to new value; null deletes the key.
            confirm: Must be True to save.

        Returns:
            JSON string with the preferences after the change, or a confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {"confirm": "Call again with confirm=True to save these preferences."}, ensure_ascii=False
            )
        try:
            return json.dumps({"values": prefs.update(values)}, ensure_ascii=False, indent=2)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def reset_ui_preferences(keep: list[str], confirm: bool = False) -> str:
        """Reset every web preference to the default except the listed keys (requires confirm=True).

        Args:
            keep: Keys to keep, e.g. ["customPalettes", "course"].
            confirm: Must be True to reset.

        Returns:
            JSON string with the preferences after the reset, or a confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {"confirm": "Call again with confirm=True to reset the preferences."}, ensure_ascii=False
            )
        return json.dumps({"values": prefs.reset(keep)}, ensure_ascii=False, indent=2)
