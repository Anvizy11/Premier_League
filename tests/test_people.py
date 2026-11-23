"""Person creation and identity checks against an isolated database."""

from datetime import date
import unittest

from tests import test_protocol as fixtures
from premier_league.services.people import calculate_age


class PeopleTests(unittest.TestCase):
    setUp = fixtures.ProtocolTests.setUp
    tearDown = fixtures.ProtocolTests.tearDown
    post = fixtures.ProtocolTests.post
    login = fixtures.ProtocolTests.login
    query = fixtures.ProtocolTests.query

    def fields(self, **changes):
        data = dict(
            first_name="Alex",
            last_name="Smith",
            birth_date="2000-11-24",
            nationality="England",
            position="DF",
            jersey_number="30",
            role="Врач",
        )
        data.update(changes)
        return data

    def test_age_at_birthday(self):
        self.assertEqual(calculate_age("2000-11-24", date(2026, 11, 23)), 25)
        self.assertEqual(calculate_age("2000-11-24", date(2026, 11, 24)), 26)
        for value in (None, "bad", "2027-01-01"):
            self.assertIsNone(calculate_age(value, date(2026, 11, 23)))

    def test_player_creation_and_team_page(self):
        self.login("club1")
        response = self.post("/teams/1/players", **self.fields())
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=players", response.location)
        row = self.query("SELECT * FROM players WHERE first_name='Alex'")[0]
        self.assertEqual(
            (row["team_id"], row["jersey_number"], row["birth_date"]), (1, 30, "2000-11-24")
        )
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"data-person-form", page.data)
        self.assertIn(b"Alex", page.data)

    def test_duplicate_identity_across_clubs_and_case(self):
        self.login("org")
        for kind in ("players", "staff"):
            self.assertEqual(self.post(f"/teams/1/{kind}", **self.fields()).status_code, 302)
            self.assertEqual(
                self.post(
                    f"/teams/2/{kind}", **self.fields(first_name="  ALEX  ", last_name="smith")
                ).status_code,
                409,
            )
            self.assertEqual(
                self.post(f"/teams/2/{kind}", **self.fields(birth_date="2000-11-25")).status_code,
                302,
            )

    def test_number_and_dates_rejected_without_insert(self):
        self.login("club1")
        for changes, status in (
            (dict(jersey_number="1"), 409),
            (dict(jersey_number="0"), 400),
            (dict(position="invalid"), 400),
            (dict(birth_date=""), 400),
            (dict(birth_date="2000-02-30"), 400),
            (dict(birth_date="2999-01-01"), 400),
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.post("/teams/1/players", **self.fields(**changes)).status_code, status
                )
        self.assertFalse(self.query("SELECT * FROM players WHERE first_name='Alex'"))

    def test_permissions_and_staff_redirect(self):
        self.login("club1")
        self.assertEqual(self.post("/teams/2/players", **self.fields()).status_code, 403)
        self.assertEqual(self.post("/teams/2/staff", **self.fields()).status_code, 403)
        response = self.post("/teams/1/staff", **self.fields())
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=staff", response.location)
        self.assertEqual(self.client.get(response.location).status_code, 200)
        self.login("ref")
        self.assertEqual(self.post("/teams/1/players", **self.fields()).status_code, 403)
