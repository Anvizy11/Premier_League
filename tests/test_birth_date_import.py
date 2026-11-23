"""Safe, repeatable birth-date import without touching the working database."""

import json
from datetime import date
import sqlite3
import unittest

from scripts.enrich_birth_dates import DATA_PATH, plan_updates, apply_updates
from premier_league.services.people import calculate_age


class BirthDateImportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript(
            """
            CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE players (id INTEGER PRIMARY KEY, team_id INTEGER,
                first_name TEXT, last_name TEXT, birth_date TEXT, jersey_number INTEGER);
            CREATE TABLE staff (id INTEGER PRIMARY KEY, team_id INTEGER,
                first_name TEXT, last_name TEXT, birth_date TEXT);
            INSERT INTO teams VALUES (1,'Club');
            INSERT INTO players VALUES (1,1,'Alex','Smith',NULL,7);
            INSERT INTO staff VALUES (1,1,'Henry','Hall',NULL);
        """
        )
        self.record = dict(
            kind="player",
            first_name="Alex",
            last_name="Smith",
            team="Club",
            birth_date="2000-01-02",
            synthetic=False,
            source_url="https://example.org/player",
        )

    def test_only_birth_date_changes_and_second_run_is_empty(self):
        updates = plan_updates(self.conn, [self.record])
        apply_updates(self.conn, updates)
        self.assertEqual(
            tuple(self.conn.execute("SELECT * FROM players").fetchone()),
            (1, 1, "Alex", "Smith", "2000-01-02", 7),
        )
        self.assertEqual(plan_updates(self.conn, [self.record]), [])

    def test_conflicting_existing_date_is_preserved(self):
        self.conn.execute("UPDATE players SET birth_date='1999-01-01'")
        with self.assertRaises(ValueError):
            plan_updates(self.conn, [self.record])
        self.assertEqual(
            self.conn.execute("SELECT birth_date FROM players").fetchone()[0], "1999-01-01"
        )

    def test_synthetic_dates_need_explicit_flag(self):
        record = dict(
            self.record,
            kind="staff",
            first_name="Henry",
            last_name="Hall",
            synthetic=True,
            source_url="",
        )
        self.assertEqual(plan_updates(self.conn, [record]), [])
        self.assertEqual(len(plan_updates(self.conn, [record], include_synthetic=True)), 1)

    def test_unknown_ambiguous_and_duplicate_records_are_rejected(self):
        with self.assertRaises(ValueError):
            plan_updates(self.conn, [dict(self.record, team="Missing")])
        with self.assertRaises(ValueError):
            plan_updates(self.conn, [self.record, self.record])
        self.conn.execute("INSERT INTO players VALUES (2,1,'Alex','Smith',NULL,8)")
        with self.assertRaises(ValueError):
            plan_updates(self.conn, [self.record])

    def test_future_date_and_missing_source_rejected(self):
        for changes in (dict(birth_date="2999-01-01"), dict(source_url="")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan_updates(self.conn, [dict(self.record, **changes)])

    def test_reviewed_dataset_has_no_age_outliers_or_duplicate_identities(self):
        data = json.loads(DATA_PATH.read_text())
        reference = date.fromisoformat(data["researched_at"])
        identities = set()
        for record in data["records"]:
            identity = (record["kind"], record["team"], record["first_name"], record["last_name"])
            self.assertNotIn(identity, identities)
            identities.add(identity)
            age = calculate_age(record["birth_date"], reference)
            self.assertIsNotNone(age, identity)
            if record["kind"] == "player":
                self.assertTrue(12 <= age <= 50, (identity, age))
            if not record["synthetic"]:
                self.assertTrue(record["source_url"].startswith("https://"), identity)
