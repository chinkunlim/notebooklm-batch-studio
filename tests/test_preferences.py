"""Web preferences (設計與自訂, layout, study memories) are recorded in the local database (ADR-009)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.preferences_repository import PreferencesRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.preferences_service import MAX_VALUE_CHARS, PreferencesService


class PreferencesTest(unittest.TestCase):
    """Saving, deleting, resetting and validating preferences through the service, HTTP and MCP."""

    def setUp(self) -> None:
        """Create an in-memory database, the service and an HTTP client."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config = AppConfig(
            data_dir=Path(self.tmpdir.name) / "data",
            notebooklm_home=Path(self.tmpdir.name) / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        self.prefs = PreferencesService(PreferencesRepository(self.session))
        app = create_app(config=self.config, service=mock.MagicMock(), study_service=mock.MagicMock())
        app.state.preferences = self.prefs
        self.http = TestClient(app)

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def test_update_saves_and_null_deletes(self) -> None:
        """Values are stored as text; null removes a key."""
        self.prefs.update({"palette": "clay", "col.stage": "30", "avatar": '{"type":"text","value":"LK"}'})
        self.prefs.update({"col.stage": None})
        self.assertEqual(self.prefs.get_all(), {"palette": "clay", "avatar": '{"type":"text","value":"LK"}'})

    def test_reset_keeps_listed_keys(self) -> None:
        """Reset removes everything except the keys asked to keep (custom palettes, current course)."""
        self.prefs.update({"palette": "clay", "customPalettes": "[]", "course": "BIO101", "layout": "split"})
        self.prefs.reset(keep=["customPalettes", "course"])
        self.assertEqual(self.prefs.get_all(), {"customPalettes": "[]", "course": "BIO101"})

    def test_bad_keys_and_values_are_refused(self) -> None:
        """Keys must be short and plain; values have a size limit; nothing is saved when one is bad."""
        for bad in ({"has space": "1"}, {"": "1"}, {"x" * 121: "1"}, {"big": "x" * (MAX_VALUE_CHARS + 1)}):
            with self.subTest(bad=list(bad)[0][:10]), self.assertRaises(ValueError):
                self.prefs.update({"ok": "1", **bad})
        self.assertEqual(self.prefs.get_all(), {})

    def test_http_round_trip(self) -> None:
        """GET returns what PUT saved; reset keeps the listed keys; a bad key is a 400."""
        self.assertEqual(self.http.get("/api/preferences").json(), {"values": {}})
        res = self.http.put("/api/preferences", json={"values": {"mode": "dark", "skin": "ring"}})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.http.get("/api/preferences").json()["values"], {"mode": "dark", "skin": "ring"})
        self.http.put("/api/preferences", json={"values": {"skin": None}})
        self.assertEqual(self.http.get("/api/preferences").json()["values"], {"mode": "dark"})
        self.assertEqual(self.http.put("/api/preferences", json={"values": {"a b": "1"}}).status_code, 400)
        self.http.post("/api/preferences/reset", json={"keep": ["mode"]})
        self.assertEqual(self.http.get("/api/preferences").json()["values"], {"mode": "dark"})

    def test_mcp_changes_need_confirm(self) -> None:
        """Reading is free; saving and resetting need confirm=True."""
        mcp = build_mcp_server(
            service=mock.MagicMock(),
            study_service=mock.MagicMock(),
            config=self.config,
            preferences=self.prefs,
        )
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertIn("confirm", json.loads(tools["set_ui_preferences"].fn({"palette": "sage"})))
        self.assertEqual(self.prefs.get_all(), {})
        tools["set_ui_preferences"].fn({"palette": "sage"}, confirm=True)
        self.assertEqual(json.loads(tools["get_ui_preferences"].fn())["values"], {"palette": "sage"})
        self.assertIn("confirm", json.loads(tools["reset_ui_preferences"].fn([])))
        tools["reset_ui_preferences"].fn([], confirm=True)
        self.assertEqual(self.prefs.get_all(), {})


if __name__ == "__main__":
    unittest.main()
