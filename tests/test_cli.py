"""Password recovery tests against an isolated database."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

from premier_league import create_app
from premier_league.database import db_connection
from premier_league.migrations import initialize_database


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(
            os.environ, {"PREMIER_LEAGUE_DATABASE": str(Path(directory.name) / "test.db")}
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.runner = self.app.test_cli_runner()
        with db_connection(write=True) as conn:
            initialize_database(conn)
            for name in ("organizer", "other"):
                conn.execute(
                    "INSERT INTO users (username,password_hash,role) VALUES (?,?,'organizer')",
                    (name, generate_password_hash("old-test-password")),
                )

    def users(self):
        with db_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]

    def test_new_password_works_and_only_target_hash_changes(self):
        before = self.users()
        response = self.runner.invoke(
            args=["reset-password", "organizer"],
            input="new-test-password\nnew-test-password\n",
        )
        self.assertEqual(response.exit_code, 0, response.output)
        self.assertNotIn("new-test-password", response.output)
        after = self.users()
        self.assertEqual(before[1], after[1])
        self.assertEqual(
            {key: value for key, value in before[0].items() if key != "password_hash"},
            {key: value for key, value in after[0].items() if key != "password_hash"},
        )
        self.assertTrue(check_password_hash(after[0]["password_hash"], "new-test-password"))
        self.assertFalse(check_password_hash(after[0]["password_hash"], "old-test-password"))
        client = self.app.test_client()
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["csrf_token"]
        response = client.post(
            "/login",
            data={"username": "organizer", "password": "new-test-password", "csrf_token": csrf},
        )
        self.assertEqual(response.status_code, 302)

    def test_unknown_user_and_short_password_leave_accounts_unchanged(self):
        before = self.users()
        response = self.runner.invoke(args=["reset-password", "missing"])
        self.assertNotEqual(response.exit_code, 0)
        self.assertIn("Пользователь не найден", response.output)
        response = self.runner.invoke(args=["reset-password", "organizer"], input="short\nshort\n")
        self.assertNotEqual(response.exit_code, 0)
        self.assertEqual(self.users(), before)

    def test_mismatched_confirmation_and_abort_leave_password_unchanged(self):
        before = self.users()
        response = self.runner.invoke(
            args=["reset-password", "organizer"], input="new-test-password\nwrong\n"
        )
        self.assertNotEqual(response.exit_code, 0)
        self.assertEqual(self.users(), before)
