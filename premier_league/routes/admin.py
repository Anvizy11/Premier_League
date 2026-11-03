"""Admin routes."""

from flask import Blueprint, render_template, abort, redirect, url_for, g
from premier_league.database import db_connection
from premier_league.auth import roles_required
from premier_league.services.protocol import match_row, form_int
from premier_league.routes.helpers import match_date_value, referee_id_value, has_match_events

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@roles_required("team_admin", "referee", "organizer")
def admin_panel():
    from premier_league.services.discipline import disciplinary_state

    with db_connection() as conn:
        teams = conn.execute("SELECT id,name FROM teams ORDER BY name").fetchall()
        matches = conn.execute(
            """SELECT m.*, h.name AS home_name, a.name AS away_name
            FROM matches m JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
            ORDER BY m.gameweek,m.id"""
        ).fetchall()
        if g.user["role"] == "team_admin":
            matches = [
                m for m in matches if g.user["team_id"] in (m["home_team_id"], m["away_team_id"])
            ]
        elif g.user["role"] == "referee":
            matches = [m for m in matches if m["referee_user_id"] == g.user["id"]]
        referees = conn.execute(
            "SELECT id,username FROM users WHERE role='referee' ORDER BY username"
        ).fetchall()
        state = disciplinary_state(conn)
        if g.user["role"] == "team_admin":
            state = {
                key: value
                for key, value in state.items()
                if value["person"]["team_id"] == g.user["team_id"]
            }
        return render_template(
            "admin.html", teams=teams, matches=matches, referees=referees, discipline=state
        )


@bp.post("/admin/create-fixture")
@roles_required("organizer")
def create_fixture():
    home_id, away_id = form_int("home_team_id"), form_int("away_team_id")
    gameweek = form_int("gameweek", 1, 38)
    date = match_date_value()
    with db_connection(write=True) as conn:
        if (
            home_id == away_id
            or conn.execute(
                "SELECT COUNT(*) FROM teams WHERE id IN (?,?)", (home_id, away_id)
            ).fetchone()[0]
            != 2
        ):
            abort(400, "Выберите две разные команды")
        referee = referee_id_value(conn)
        match_id = conn.execute(
            "INSERT INTO matches (gameweek,home_team_id,away_team_id,status,is_finished,referee_user_id,match_date) VALUES (?,?,?,'SCHEDULED',0,?,?)",
            (gameweek, home_id, away_id, referee, date),
        ).lastrowid
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/assign-referee")
@roles_required("organizer")
def assign_referee(match_id):
    with db_connection(write=True) as conn:
        match_row(conn, match_id, editable=True)
        if has_match_events(conn, match_id):
            abort(409, "Сначала удалите события, чтобы изменить назначение и дату")
        referee = referee_id_value(conn)
        date = match_date_value()
        conn.execute(
            "UPDATE matches SET referee_user_id=?,match_date=? WHERE id=?",
            (referee, date, match_id),
        )
        conn.execute(
            "UPDATE match_team_submissions SET status='SUBMITTED',checked_by=NULL WHERE match_id=? AND status='APPROVED'",
            (match_id,),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))
