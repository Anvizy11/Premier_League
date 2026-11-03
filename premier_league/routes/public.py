"""Public routes."""

from flask import Blueprint, render_template, abort
from premier_league.database import db_connection
from premier_league.services.standings import (
    get_standings,
    get_top_scorers,
    get_disciplinary_leaders,
)

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    return render_template(
        "standings.html",
        standings=get_standings(),
        top_scorers=get_top_scorers(limit=None),
        disciplinary_leaders=get_disciplinary_leaders(),
    )


@bp.route("/teams")
def teams_list():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                t.id, 
                t.name, 
                t.short_name, 
                t.city, 
                t.stadium,
                s.first_name AS coach_fn,
                s.last_name AS coach_ln,
                s.nationality AS coach_nat,
                COUNT(p.id) AS player_count
            FROM teams t
            LEFT JOIN staff s ON t.id = s.team_id AND s.role = 'Head Coach'
            LEFT JOIN players p ON t.id = p.team_id
            GROUP BY t.id
            ORDER BY t.name ASC
        """
        )
        teams = cursor.fetchall()
    return render_template("teams.html", teams=teams)


@bp.route("/teams/<int:team_id>")
def team_detail(team_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        team = cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            abort(404)

        players = cursor.execute(
            """
            SELECT * FROM players
            WHERE team_id = ?
            ORDER BY
                CASE position
                    WHEN 'GK' THEN 1
                    WHEN 'DF' THEN 2
                    WHEN 'MF' THEN 3
                    WHEN 'FW' THEN 4
                END, jersey_number ASC
        """,
            (team_id,),
        ).fetchall()

        staff = cursor.execute(
            "SELECT * FROM staff WHERE team_id = ? ORDER BY id ASC", (team_id,)
        ).fetchall()
        from premier_league.services.discipline import disciplinary_state

        state = disciplinary_state(conn)
        players = [dict(p, is_suspended=state["player", p["id"]]["blocked"]) for p in players]
        staff = [dict(p, is_suspended=state["staff", p["id"]]["blocked"]) for p in staff]
        return render_template("team_detail.html", team=team, players=players, staff=staff)


@bp.route("/players/<int:player_id>")
def player_detail(player_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT p.*, t.name AS team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.id = ?
        """
        player = cursor.execute(query, (player_id,)).fetchone()
        if not player:
            abort(404)

        stats = {"appearances": 0, "goals": 0, "yellow_cards": 0, "red_cards": 0, "minutes": 0}

        # Считаем только из утвержденных матчей
        events = cursor.execute(
            """
            SELECT e.event_type, COUNT(*) as cnt
            FROM match_events e
            JOIN matches m ON e.match_id = m.id
            WHERE e.player_id = ? AND m.status = 'VERIFIED'
            GROUP BY e.event_type
        """,
            (player_id,),
        ).fetchall()

        for event in events:
            if event["event_type"] in ("GOAL", "PENALTY"):
                stats["goals"] += event["cnt"]
            elif event["event_type"] == "YELLOW_CARD":
                stats["yellow_cards"] += event["cnt"]
            elif event["event_type"] == "RED_CARD":
                stats["red_cards"] += event["cnt"]

        minutes_row = cursor.execute(
            """
            SELECT SUM(ml.minutes_played) as total_min, SUM(CASE WHEN ml.is_starter = 1 OR EXISTS (SELECT 1 FROM match_substitutions ms WHERE ms.match_id = ml.match_id AND ms.player_in_id = ml.player_id) THEN 1 ELSE 0 END) as apps
            FROM match_lineups ml
            JOIN matches m ON ml.match_id = m.id
            WHERE ml.player_id = ? AND m.status = 'VERIFIED'
        """,
            (player_id,),
        ).fetchone()

        if minutes_row:
            stats["minutes"] = minutes_row["total_min"] or 0
            stats["appearances"] = minutes_row["apps"] or 0

        stats["red_cards"] += conn.execute(
            """SELECT COUNT(*) FROM (
            SELECT e.match_id FROM match_events e JOIN matches m ON m.id=e.match_id
            WHERE m.status='VERIFIED' AND e.player_id=? AND e.event_type='YELLOW_CARD'
            GROUP BY e.match_id HAVING COUNT(*)>=2)""",
            (player_id,),
        ).fetchone()[0]
        from premier_league.services.discipline import disciplinary_state

        player = dict(player, is_suspended=disciplinary_state(conn)["player", player_id]["blocked"])
        return render_template("player_detail.html", player=player, stats=stats)
