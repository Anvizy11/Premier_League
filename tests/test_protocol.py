"""Integration tests with an independent temporary SQLite database per test."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from premier_league import create_app
from premier_league.database import db_connection
from premier_league.services.discipline import disciplinary_state
from werkzeug.security import generate_password_hash


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("PREMIER_LEAGUE_DATABASE")
        os.environ["PREMIER_LEAGUE_DATABASE"] = str(Path(self.temp.name) / "test.db")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()
        with db_connection() as conn:
            from premier_league.migrations import initialize_database

            initialize_database(conn)
            for team in (1, 2, 3):
                conn.execute(
                    "INSERT INTO teams (id,name,short_name,stadium,city) VALUES (?,?,?,?,?)",
                    (team, f"Team {team}", f"T{team}", "Stadium", "City"),
                )
                for i in range(1, 27):
                    conn.execute(
                        "INSERT INTO players (id,team_id,first_name,last_name,jersey_number,position,nationality) VALUES (?,?,?,?,?,?,?)",
                        (
                            team * 100 + i,
                            team,
                            "Player",
                            str(i),
                            i,
                            "GK" if i == 1 else "DF",
                            "England",
                        ),
                    )
                for i in range(1, 12):
                    conn.execute(
                        "INSERT INTO staff (id,team_id,first_name,last_name,role,nationality) VALUES (?,?,?,?,?,?)",
                        (
                            team * 100 + i,
                            team,
                            "Staff",
                            str(i),
                            "Главный тренер" if i == 1 else "Врач" if i == 2 else "Аналитик",
                            "England",
                        ),
                    )
            for uid, name, role, team in [
                (1, "club1", "team_admin", 1),
                (2, "club2", "team_admin", 2),
                (3, "club3", "team_admin", 3),
                (4, "ref", "referee", None),
                (5, "other_ref", "referee", None),
                (6, "org", "organizer", None),
            ]:
                conn.execute(
                    "INSERT INTO users (id,username,password_hash,role,team_id) VALUES (?,?,?,?,?)",
                    (uid, name, generate_password_hash("test-password"), role, team),
                )
            conn.execute(
                "INSERT INTO matches (id,gameweek,home_team_id,away_team_id,status,referee_user_id,match_date) VALUES (1,1,1,2,'SCHEDULED',4,'2026-11-01T18:00')"
            )

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("PREMIER_LEAGUE_DATABASE", None)
        else:
            os.environ["PREMIER_LEAGUE_DATABASE"] = self.previous
        self.temp.cleanup()

    def post(self, path, **data):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            data["csrf_token"] = session["csrf_token"]
        return self.client.post(path, data=data)

    def login(self, name):
        self.assertEqual(
            self.post("/login", username=name, password="test-password").status_code, 302
        )

    def query(self, sql, args=()):
        with db_connection() as conn:
            return conn.execute(sql, args).fetchall()

    def state(self, before=None):
        with db_connection() as conn:
            match = (
                conn.execute("SELECT * FROM matches WHERE id=?", (before,)).fetchone()
                if before
                else None
            )
            return disciplinary_state(conn, match)

    def roster(self, team=1, count=11, bench=2, staff=2, match=1):
        return self.post(
            f"/matches/{match}/lineups",
            starters=[str(team * 100 + i) for i in range(1, count + 1)],
            bench=[str(team * 100 + i) for i in range(count + 1, count + bench + 1)],
            staff=[str(team * 100 + i) for i in range(1, staff + 1)],
        )

    def prepare(self):
        for team in (1, 2):
            self.login(f"club{team}")
            self.assertEqual(self.roster(team).status_code, 302)
            self.assertEqual(self.post("/matches/1/submit-lineup").status_code, 302)
        self.login("ref")
        self.assertEqual(
            self.post(
                "/matches/1/officials",
                referee_name="Michael Oliver",
                assistant_one="Stuart Burt",
                assistant_two="Gary Beswick",
                fourth_official="Anthony Taylor",
            ).status_code,
            302,
        )
        for team in (1, 2):
            self.assertEqual(self.post(f"/matches/1/check-lineup/{team}").status_code, 302)

    def event(self, player=102, kind="GOAL", minute=10):
        return self.post("/matches/1/add-event", player_id=player, event_type=kind, minute=minute)

    def finish(self):
        self.login("ref")
        self.assertEqual(self.post("/matches/1/submit-for-review").status_code, 302)
        self.login("org")
        self.assertEqual(self.post("/matches/1/verify-protocol").status_code, 302)

    def historical(
        self, mid, yellows=0, red=False, kind="player", subject=102, roster=False, status="VERIFIED"
    ):
        with db_connection() as conn:
            conn.execute(
                "INSERT INTO matches (id,gameweek,home_team_id,away_team_id,status,match_date,home_score,away_score) VALUES (?,?,1,2,?,?,0,0)",
                (mid, mid, status, f"2026-10-{mid:02d}T18:00"),
            )
            table, field = (
                ("match_events", "player_id") if kind == "player" else ("staff_events", "staff_id")
            )
            for i in range(yellows):
                conn.execute(
                    f"INSERT INTO {table} (match_id,team_id,{field},event_type,minute) VALUES (?,1,?,'YELLOW_CARD',?)",
                    (mid, subject, 10 + i * 10),
                )
            if red:
                conn.execute(
                    f"INSERT INTO {table} (match_id,team_id,{field},event_type,minute) VALUES (?,1,?,'RED_CARD',40)",
                    (mid, subject),
                )
            if roster or yellows or red:
                if kind == "player":
                    conn.execute(
                        "INSERT INTO match_lineups (match_id,player_id,team_id,is_starter) VALUES (?,?,1,1)",
                        (mid, subject),
                    )
                else:
                    conn.execute(
                        "INSERT INTO match_staff (match_id,staff_id,team_id,role) VALUES (?,?,1,'Врач')",
                        (mid, subject),
                    )

    def test_public_pages_csrf_and_match_visibility(self):
        for path in ["/", "/teams", "/teams/1", "/players/101", "/login"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 302)
        self.assertEqual(self.client.post("/logout").status_code, 400)
        self.login("club3")
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 403)
        self.login("other_ref")
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 403)
        self.login("org")
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)

    def test_team_isolation_and_staff_management(self):
        self.login("club1")
        self.assertEqual(self.roster(2).status_code, 403)
        self.assertEqual(
            self.post(
                "/teams/2/staff", first_name="A", last_name="B", role="Врач", nationality="RU"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                "/teams/1/staff",
                first_name="A",
                last_name="B",
                role="Тренер вратарей",
                nationality="RU",
            ).status_code,
            302,
        )
        self.assertEqual(self.event().status_code, 403)
        self.assertEqual(self.post("/matches/1/verify-protocol").status_code, 403)
        self.assertEqual(self.roster().status_code, 302)
        self.login("club2")
        self.assertEqual(self.roster(2).status_code, 302)
        self.assertEqual(len(self.query("SELECT * FROM match_lineups WHERE team_id=1")), 13)

    def test_limits_players_bench_and_staff(self):
        self.login("club1")
        for starters, bench, staff in [(6, 1, 2), (12, 1, 2), (11, 13, 2), (7, 0, 1), (7, 0, 11)]:
            self.assertEqual(
                self.roster(count=starters, bench=bench, staff=staff).status_code,
                400,
                (starters, bench, staff),
            )
        self.assertEqual(self.roster(count=7, bench=12, staff=10).status_code, 302)
        self.assertEqual(
            self.post(
                "/matches/1/lineups",
                starters=[str(i) for i in range(101, 108)],
                bench=["101"],
                staff=["101", "102"],
            ).status_code,
            400,
        )
        with db_connection() as conn:
            conn.execute("UPDATE staff SET role='Массажист' WHERE id=102")
        self.assertEqual(self.roster().status_code, 400)
        self.assertEqual(len(self.query("SELECT * FROM match_lineups")), 19)

    def test_submit_and_referee_checks(self):
        self.login("club1")
        self.roster()
        self.post("/matches/1/submit-lineup")
        self.assertEqual(self.roster().status_code, 409)
        self.login("other_ref")
        self.assertEqual(self.post("/matches/1/check-lineup/1").status_code, 403)
        self.login("ref")
        self.assertEqual(self.event().status_code, 409)
        self.assertEqual(self.post("/matches/1/check-lineup/1").status_code, 302)
        self.assertEqual(self.post("/matches/1/return-lineup/1").status_code, 302)
        self.login("club1")
        self.assertEqual(self.roster(count=7).status_code, 302)

    def test_full_match_and_role_restrictions(self):
        self.prepare()
        self.assertEqual(self.event().status_code, 302)
        self.assertEqual(self.event(202, "OWN_GOAL", 20).status_code, 302)
        self.assertEqual(
            self.post(
                "/matches/1/make-substitution", player_out_id=102, player_in_id=112, minute=60
            ).status_code,
            302,
        )
        self.assertEqual(self.event(112, "YELLOW_CARD", 65).status_code, 302)
        self.assertEqual(self.event(112, "YELLOW_CARD", 80).status_code, 302)
        self.assertEqual(self.event(112, "GOAL", 85).status_code, 400)
        self.assertEqual(
            self.query("SELECT minutes_played FROM match_lineups WHERE player_id=112")[0][0], 20
        )
        self.assertEqual(self.post("/matches/1/verify-protocol").status_code, 403)
        self.assertEqual(self.post("/matches/1/return-lineup/1").status_code, 409)
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)
        self.finish()
        match = self.query("SELECT * FROM matches WHERE id=1")[0]
        self.assertEqual(
            (match["home_score"], match["away_score"], match["status"]), (2, 0, "VERIFIED")
        )
        self.assertEqual(self.state()["player", 112]["remaining"], 1)
        self.assertEqual(self.state()["player", 112]["yellow_matches"], 0)
        with patch("premier_league.routes.public.render_template", return_value="ok") as render:
            self.client.get("/players/113")
            self.assertEqual(render.call_args.kwargs["stats"]["appearances"], 0)
        with patch("premier_league.routes.public.render_template", return_value="ok") as render:
            self.client.get("/players/112")
            self.assertEqual(render.call_args.kwargs["stats"]["red_cards"], 1)
        self.assertEqual(self.post("/matches/1/reopen-protocol").status_code, 302)
        self.assertEqual(self.state()["player", 112]["remaining"], 0)

    def test_double_yellow_excludes_game_preserves_prior_accumulation(self):
        for mid in (2, 3, 4, 5):
            self.historical(mid, yellows=1)
        self.historical(6, yellows=2)
        state = self.state()["player", 102]
        self.assertEqual((state["yellow_matches"], state["remaining"]), (4, 1))
        self.historical(7)
        self.assertEqual(self.state()["player", 102]["remaining"], 0)
        self.historical(8, yellows=1)
        state = self.state()["player", 102]
        self.assertEqual((state["yellow_matches"], state["remaining"]), (5, 1))

    def test_straight_red_keeps_same_match_and_previous_yellows(self):
        self.historical(2, yellows=1)
        self.historical(3, yellows=1, red=True)
        state = self.state()["player", 102]
        self.assertEqual((state["yellow_matches"], state["remaining"]), (2, 1))
        self.historical(4, status="DRAFT")
        self.assertEqual(self.state()["player", 102]["remaining"], 1)
        self.historical(5, roster=True)
        self.assertEqual(self.state()["player", 102]["remaining"], 1)
        self.historical(6)
        self.assertEqual(self.state()["player", 102]["remaining"], 0)

    def test_five_yellows_block_roster_and_serve_next_verified_absence(self):
        for mid in range(2, 7):
            self.historical(mid, yellows=1)
        self.login("club1")
        self.assertEqual(self.roster().status_code, 400)
        self.historical(7, status="PENDING_REVIEW")
        self.assertEqual(self.state()["player", 102]["remaining"], 1)
        with db_connection() as conn:
            conn.execute("UPDATE matches SET status='VERIFIED' WHERE id=7")
        self.assertEqual(self.state()["player", 102]["remaining"], 0)
        self.assertEqual(self.roster().status_code, 302)

    def test_staff_cards_and_kdk_extension(self):
        self.prepare()
        self.assertEqual(
            self.post(
                "/matches/1/staff-event", staff_id=102, event_type="RED_CARD", minute=30
            ).status_code,
            302,
        )
        self.assertEqual(
            self.post(
                "/matches/1/staff-event", staff_id=102, event_type="YELLOW_CARD", minute=40
            ).status_code,
            400,
        )
        self.finish()
        self.assertEqual(self.state()["staff", 102]["remaining"], 1)
        self.assertEqual(
            self.post(
                "/discipline/decision",
                match_id=1,
                subject_type="staff",
                subject_id=102,
                reason="RED_CARD",
                total_games=3,
                explanation="Решение КДК №1",
            ).status_code,
            302,
        )
        self.assertEqual(self.state()["staff", 102]["remaining"], 3)
        self.assertEqual(
            self.post(
                "/discipline/decision",
                match_id=1,
                subject_type="staff",
                subject_id=102,
                reason="RED_CARD",
                total_games=0,
                explanation="x",
            ).status_code,
            400,
        )
        self.login("club1")
        self.assertEqual(
            self.post(
                "/discipline/decision",
                match_id=1,
                subject_type="staff",
                subject_id=102,
                reason="RED_CARD",
                total_games=5,
                explanation="x",
            ).status_code,
            403,
        )
        self.login("org")
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_late_kdk_extension_only_credits_actual_served_games(self):
        self.historical(2, red=True)
        self.historical(3)  # Serves the automatic one-game ban.
        self.historical(4, roster=True)  # Eligible again.
        self.historical(5)  # Ordinary absence, not a served suspension.
        self.login("org")
        response = self.post(
            "/discipline/decision",
            match_id=2,
            subject_type="player",
            subject_id=102,
            reason="RED_CARD",
            total_games=3,
            explanation="Позднее решение КДК",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.state()["player", 102]["remaining"], 2)
        self.assertEqual(self.state(before=4)["player", 102]["remaining"], 0)
        self.historical(6)
        self.assertEqual(self.state()["player", 102]["remaining"], 1)
        self.post(
            "/discipline/decision",
            match_id=2,
            subject_type="player",
            subject_id=102,
            reason="RED_CARD",
            total_games=4,
            explanation="Уточнение КДК",
        )
        self.assertEqual(self.state()["player", 102]["remaining"], 2)
        self.assertEqual(len(self.query("SELECT * FROM disciplinary_decision_history")), 2)

    def test_staff_two_yellows_and_prior_records(self):
        self.historical(2, yellows=1, kind="staff")
        self.historical(3, yellows=2, kind="staff")
        state = self.state()["staff", 102]
        self.assertEqual((state["yellow_matches"], state["remaining"]), (1, 1))

    def test_invalid_substitution_rolls_back(self):
        self.prepare()
        self.assertEqual(
            self.post(
                "/matches/1/make-substitution", player_out_id=102, player_in_id=212, minute=60
            ).status_code,
            400,
        )
        self.assertEqual(len(self.query("SELECT * FROM match_substitutions")), 0)
        self.assertEqual(self.event(301).status_code, 400)
        self.assertEqual(self.event(112).status_code, 400)
        self.assertEqual(self.event(102, "GOAL", 100).status_code, 400)

    def test_bench_card_dismissal_blocks_substitution(self):
        self.prepare()
        self.assertEqual(self.event(112, "YELLOW_CARD", 10).status_code, 302)
        self.assertEqual(self.event(112, "YELLOW_CARD", 20).status_code, 302)
        self.assertEqual(
            self.post(
                "/matches/1/make-substitution", player_out_id=102, player_in_id=112, minute=60
            ).status_code,
            400,
        )
        self.assertEqual(
            self.query("SELECT minutes_played FROM match_lineups WHERE player_id=112")[0][0], 0
        )

    def test_delete_second_yellow_restores_minutes_and_removal(self):
        self.prepare()
        self.event(102, "YELLOW_CARD", 10)
        self.event(102, "YELLOW_CARD", 60)
        self.assertEqual(
            self.query("SELECT minutes_played FROM match_lineups WHERE player_id=102")[0][0], 60
        )
        event = self.query("SELECT id FROM match_events WHERE minute=60")[0][0]
        self.assertEqual(self.post(f"/matches/1/delete-event/{event}").status_code, 302)
        self.assertEqual(
            self.query("SELECT minutes_played FROM match_lineups WHERE player_id=102")[0][0], 90
        )
        self.assertEqual(self.event(102, "GOAL", 80).status_code, 302)

    def test_ban_extension_preserves_yellows_and_approved_roster_is_rechecked(self):
        for mid in (2, 3, 4, 5):
            self.historical(mid, yellows=1)
        self.prepare()
        self.historical(6, yellows=1)
        self.assertEqual(self.event().status_code, 400)
        self.assertEqual(len(self.query("SELECT * FROM match_events WHERE match_id=1")), 0)
        self.login("org")
        self.assertEqual(
            self.post(
                "/discipline/decision",
                match_id=6,
                subject_type="player",
                subject_id=102,
                reason="YELLOW_LIMIT",
                total_games=3,
                explanation="КДК",
            ).status_code,
            302,
        )
        self.assertEqual(self.state()["player", 102]["yellow_matches"], 5)
        self.historical(7)
        self.assertEqual(self.state()["player", 102]["remaining"], 2)

    def test_out_of_order_verification_rejects_new_historical_conflict(self):
        self.prepare()
        self.event(102, "RED_CARD", 30)
        with db_connection() as conn:
            conn.execute(
                "INSERT INTO matches (id,gameweek,home_team_id,away_team_id,status,match_date,home_score,away_score) VALUES (2,2,1,2,'VERIFIED','2026-11-02T18:00',0,0)"
            )
            conn.execute(
                "INSERT INTO match_lineups (match_id,player_id,team_id,is_starter) VALUES (2,102,1,1)"
            )
        self.post("/matches/1/submit-for-review")
        self.login("org")
        self.assertEqual(self.post("/matches/1/verify-protocol").status_code, 409)
        self.assertEqual(
            self.query("SELECT status FROM matches WHERE id=1")[0][0], "PENDING_REVIEW"
        )

    def test_create_match_assignments_and_cli_accounts(self):
        self.login("org")
        self.assertEqual(
            self.post(
                "/admin/create-fixture",
                home_team_id=1,
                away_team_id=2,
                gameweek=2,
                match_date="2026-11-03T18:00",
                referee_user_id=4,
            ).status_code,
            302,
        )
        self.assertEqual(
            self.post(
                "/admin/create-fixture",
                home_team_id=1,
                away_team_id=2,
                gameweek=2,
                match_date="bad",
                referee_user_id=4,
            ).status_code,
            400,
        )
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-user", "new_club", "--role", "team_admin", "--team-id", "1"],
            input="long-password\nlong-password\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        result = runner.invoke(
            args=["create-user", "bad_club", "--role", "team_admin"],
            input="long-password\nlong-password\n",
        )
        self.assertNotEqual(result.exit_code, 0)

    def digest(self):
        from premier_league.services.confirmations import protocol_hash

        with db_connection() as conn:
            return protocol_hash(conn, 1)

    def organizer_match(self):
        self.login("org")
        for team in (1, 2):
            response = self.post(
                "/matches/1/lineups",
                team_id=team,
                starters=[str(team * 100 + i) for i in range(1, 12)],
                bench=[str(team * 100 + 12)],
                staff=[str(team * 100 + 1), str(team * 100 + 2)],
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.post(
                "/matches/1/officials",
                referee_name="Michael Oliver",
                assistant_one="Stuart Burt",
                assistant_two="Gary Beswick",
                fourth_official="Anthony Taylor",
            ).status_code,
            302,
        )
        self.assertEqual(self.event().status_code, 302)
        self.assertEqual(self.post("/matches/1/submit-for-review").status_code, 302)
        self.assertEqual(self.post("/matches/1/verify-protocol").status_code, 302)

    def test_organizer_can_complete_protocol_without_participant_approvals(self):
        self.organizer_match()
        self.assertEqual(self.query("SELECT status FROM matches WHERE id=1")[0][0], "VERIFIED")
        self.assertEqual(len(self.query("SELECT * FROM protocol_confirmations")), 0)
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)
        self.assertEqual(
            self.post("/matches/1/confirm", content_hash=self.digest()).status_code, 403
        )
        for name in ("club1", "club2", "ref"):
            self.login(name)
            self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)
            self.assertEqual(
                self.post("/matches/1/confirm", content_hash=self.digest()).status_code, 302
            )
        self.assertEqual(len(self.query("SELECT * FROM protocol_confirmations")), 3)
        self.login("club3")
        self.assertEqual(
            self.post("/matches/1/confirm", content_hash=self.digest()).status_code, 403
        )
        self.login("other_ref")
        self.assertEqual(
            self.post("/matches/1/confirm", content_hash=self.digest()).status_code, 403
        )

    def test_confirmation_is_invalidated_by_changes_and_stale_form_is_rejected(self):
        self.organizer_match()
        old_hash = self.digest()
        self.login("club1")
        self.post("/matches/1/confirm", content_hash=old_hash)
        self.login("org")
        self.post("/matches/1/reopen-protocol")
        self.assertEqual(self.event(103, "GOAL", 20).status_code, 302)
        self.post("/matches/1/submit-for-review")
        from premier_league.services.confirmations import confirmation_status

        with db_connection() as conn:
            status = confirmation_status(
                conn, conn.execute("SELECT * FROM matches WHERE id=1").fetchone()
            )
        self.assertFalse(status[0]["valid"])
        self.login("club1")
        self.assertEqual(self.post("/matches/1/confirm", content_hash=old_hash).status_code, 409)
        self.assertEqual(
            self.post("/matches/1/confirm", content_hash=self.digest()).status_code, 302
        )

    def test_organizer_editing_existing_roster_keeps_event_validation(self):
        self.organizer_match()
        self.post("/matches/1/reopen-protocol")
        self.assertEqual(
            self.post(
                "/matches/1/lineups",
                team_id=1,
                starters=["101"] + [str(i) for i in range(103, 113)],
                bench=[],
                staff=["101", "102"],
            ).status_code,
            400,
        )
        self.assertEqual(len(self.query("SELECT * FROM match_lineups WHERE player_id=102")), 1)
        self.assertEqual(
            self.post(
                "/teams/2/staff", first_name="A", last_name="B", role="Врач", nationality="RU"
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)

    def test_official_directory_optional_var_and_clearing(self):
        self.login("org")
        self.assertGreaterEqual(len(self.query("SELECT * FROM officials")), 12)
        fields = dict(
            referee_name="Michael Oliver",
            assistant_one="Stuart Burt",
            assistant_two="Gary Beswick",
            fourth_official="Anthony Taylor",
        )
        self.assertEqual(
            self.post(
                "/matches/1/officials",
                **fields,
                var_official="Chris Kavanagh",
                avar_official="Simon Bennett",
            ).status_code,
            302,
        )
        match = self.query("SELECT * FROM matches WHERE id=1")[0]
        self.assertEqual(
            (match["var_official"], match["avar_official"]), ("Chris Kavanagh", "Simon Bennett")
        )
        digest = self.digest()
        self.assertEqual(self.post("/matches/1/officials", **fields).status_code, 302)
        self.assertNotEqual(self.digest(), digest)
        self.assertEqual(self.query("SELECT var_official FROM matches")[0][0], "")
        fields["assistant_one"] = "Unknown Official"
        self.assertEqual(self.post("/matches/1/officials", **fields).status_code, 400)

    def test_manual_goalkeeper_captain_foreign_and_staff_sort(self):
        self.login("club1")
        response = self.post(
            "/matches/1/lineups",
            starters=[str(i) for i in range(102, 109)],
            bench=["101"],
            goalkeepers=["102"],
            captains=["103"],
            staff=["102", "101"],
        )
        self.assertEqual(response.status_code, 302)
        flags = self.query(
            "SELECT is_goalkeeper,is_captain FROM match_lineups WHERE player_id=103"
        )[0]
        self.assertEqual(tuple(flags), (0, 1))
        self.assertEqual(
            self.query("SELECT is_goalkeeper FROM match_lineups WHERE player_id=102")[0][0], 1
        )
        self.assertEqual(
            self.query("SELECT is_goalkeeper FROM match_lineups WHERE player_id=101")[0][0], 1
        )
        from premier_league.services.protocol import is_foreign

        self.assertFalse(is_foreign("Англия"))
        self.assertFalse(is_foreign(" England "))
        self.assertTrue(is_foreign("Spain"))
        with patch("premier_league.routes.matches.render_template", return_value="ok") as render:
            self.client.get("/matches/1/protocol")
            panel = render.call_args.kwargs["panels"][0]
            self.assertTrue(panel["staff"][0]["is_head_coach"])
            self.assertFalse(panel["players"][0]["is_foreign"])
        self.assertEqual(
            self.post(
                "/matches/1/lineups",
                starters=[str(i) for i in range(101, 108)],
                bench=[],
                captains=["102", "103"],
                staff=["101", "102"],
            ).status_code,
            400,
        )

    def test_event_forms_only_appear_after_both_rosters_and_officials(self):
        self.login("org")

        def can_edit_events():
            with patch(
                "premier_league.routes.matches.render_template", return_value="ok"
            ) as render:
                self.client.get("/matches/1/protocol")
                return render.call_args.kwargs["event_editable"]

        self.assertFalse(can_edit_events())
        for team in (1, 2):
            self.post(
                "/matches/1/lineups",
                team_id=team,
                starters=[str(team * 100 + i) for i in range(1, 8)],
                staff=[str(team * 100 + 1), str(team * 100 + 2)],
            )
            self.assertFalse(can_edit_events())
        self.post(
            "/matches/1/officials",
            referee_name="Michael Oliver",
            assistant_one="Stuart Burt",
            assistant_two="Gary Beswick",
            fourth_official="Anthony Taylor",
        )
        self.assertTrue(can_edit_events())
        self.assertEqual(self.client.get("/matches/1/protocol").status_code, 200)
        self.assertEqual(self.event().status_code, 302)

    def test_marks_participate_in_protocol_confirmations(self):
        self.organizer_match()
        original = self.digest()
        self.post("/matches/1/reopen-protocol")
        self.assertEqual(
            self.post(
                "/matches/1/lineups",
                team_id=1,
                starters=[str(i) for i in range(101, 112)],
                bench=["112"],
                staff=["101", "102"],
                captains=["103"],
            ).status_code,
            302,
        )
        self.assertNotEqual(self.digest(), original)

    def test_scoring_requires_substitution_before_event_minute(self):
        self.prepare()
        for kind in ("GOAL", "PENALTY", "OWN_GOAL"):
            self.assertEqual(self.event(112, kind, 30).status_code, 400)
        self.assertEqual(
            self.post(
                "/matches/1/make-substitution", player_out_id=102, player_in_id=112, minute=60
            ).status_code,
            302,
        )
        for kind in ("GOAL", "PENALTY", "OWN_GOAL"):
            self.assertEqual(self.event(112, kind, 59).status_code, 400)
            self.assertEqual(self.event(112, kind, 61).status_code, 302)
            self.assertEqual(self.event(102, kind, 61).status_code, 400)
        self.assertEqual(self.post("/matches/1/delete-substitution/1").status_code, 400)
        self.assertEqual(len(self.query("SELECT * FROM match_substitutions")), 1)

    def test_off_field_card_labels_follow_event_time(self):
        self.prepare()
        self.event(112, "YELLOW_CARD", 30)
        self.post("/matches/1/make-substitution", player_out_id=102, player_in_id=112, minute=60)
        self.event(112, "YELLOW_CARD", 70)
        self.event(102, "YELLOW_CARD", 75)
        with patch("premier_league.routes.matches.render_template", return_value="ok") as render:
            self.client.get("/matches/1/protocol")
            flags = [event["off_field"] for event in render.call_args.kwargs["events"]]
            self.assertEqual(flags, [True, False, True])
        self.assertIn("не на поле", self.client.get("/matches/1/protocol").text)

    def test_staff_cannot_have_scoring_events(self):
        self.prepare()
        for kind in ("GOAL", "PENALTY", "OWN_GOAL"):
            self.assertEqual(
                self.post(
                    "/matches/1/staff-event", staff_id=101, event_type=kind, minute=10
                ).status_code,
                400,
            )
        self.assertEqual(len(self.query("SELECT * FROM staff_events")), 0)

    def test_idempotent_migration_and_legacy_accounts(self):
        from premier_league.migrations import initialize_database

        with db_connection() as conn:
            # No assigned referee references users in this test's legacy snapshot.
            conn.execute("UPDATE matches SET referee_user_id=NULL")
            conn.execute("DROP TABLE users")
            conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY,username TEXT UNIQUE,password_hash TEXT,role TEXT CHECK(role IN ('admin','reviewer')))"
            )
            conn.execute("INSERT INTO users VALUES (1,'legacy','hash','admin')")
            initialize_database(conn)
            initialize_database(conn)
            self.assertEqual(conn.execute("SELECT role FROM users").fetchone()[0], "organizer")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0], 78)
            self.assertEqual(len(conn.execute("PRAGMA foreign_key_check").fetchall()), 0)


if __name__ == "__main__":
    unittest.main()
