"""Application wiring checks independent of production data."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from premier_league import create_app
from premier_league.database import DATABASE_NAME
from premier_league.paths import PROJECT_ROOT, SCHEMA_PATH, SESSION_KEY_PATH


class ApplicationTests(unittest.TestCase):
    def test_factory_creates_independent_sessions(self):
        first = create_app({"TESTING": True, "SECRET_KEY": "first-test-key"})
        second = create_app({"TESTING": True, "SECRET_KEY": "second-test-key"})
        first_client = first.test_client()
        second_client = second.test_client()
        with first_client.session_transaction() as session:
            session["marker"] = "first-app"
        with second_client.session_transaction() as session:
            self.assertNotIn("marker", session)
        self.assertNotEqual(first.secret_key, second.secret_key)

    def test_assets_and_templates_resolve_outside_project_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                app = create_app({"TESTING": True, "SECRET_KEY": "test-key"})
                client = app.test_client()
                self.assertEqual(client.get("/login").status_code, 200)
                for asset in (
                    "css/protocol.css",
                    "js/combobox.js",
                    "js/lineups.js",
                    "js/events.js",
                ):
                    with client.get(f"/static/{asset}") as response:
                        self.assertEqual(response.status_code, 200, asset)
                database = Path(directory) / "isolated.db"
                with patch.dict(os.environ, {"PREMIER_LEAGUE_DATABASE": str(database)}):
                    result = app.test_cli_runner().invoke(args=["init-db"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertTrue(database.is_file())
                self.assertTrue(SCHEMA_PATH.is_file())
                self.assertEqual(Path(DATABASE_NAME), PROJECT_ROOT / "premier_league.db")
                self.assertEqual(SESSION_KEY_PATH, PROJECT_ROOT / ".session_key")
            finally:
                os.chdir(previous)

    def test_maintenance_module_imports_have_no_database_effects(self):
        # Importing a script must not execute its destructive main operation.
        with patch("premier_league.database.db_connection") as connection:
            for name in (
                "seed_season_26_27",
                "enrich_nationalities",
                "generate_fixtures",
                "migrate_protocols",
            ):
                importlib.import_module(f"scripts.{name}")
            connection.assert_not_called()
