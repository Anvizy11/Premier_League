"""Lineups routes."""

from flask import Blueprint, abort, request, redirect, url_for, g
from premier_league.database import db_connection
from premier_league.auth import roles_required
from premier_league.services.protocol import (
    calculate_minutes,
    validate_team_lineup,
    require_referee,
    validate_staff_events,
)
from premier_league.routes.helpers import team_match, has_match_events, selected_ids

bp = Blueprint("lineups", __name__)


@bp.post("/matches/<int:match_id>/lineups")
@roles_required("team_admin", "organizer")
def save_lineups(match_id):
    starters, bench, staff = selected_ids("starters"), selected_ids("bench"), selected_ids("staff")
    if set(starters) & set(bench):
        abort(400, "Игрок не может быть одновременно в старте и запасе")
    with db_connection(write=True) as conn:
        match, team = team_match(conn, match_id)
        player_rows = {
            r["id"]: r
            for r in conn.execute("SELECT id,position FROM players WHERE team_id=?", (team,))
        }
        player_ids = set(player_rows)
        keepers, captains = selected_ids("goalkeepers"), selected_ids("captains")
        if not set(keepers + captains) <= set(starters + bench) or len(captains) > 1:
            abort(400, "Пометки должны относиться к выбранным игрокам; капитан только один")
        staff_rows = {
            r["id"]: r for r in conn.execute("SELECT * FROM staff WHERE team_id=?", (team,))
        }
        if not set(starters + bench) <= player_ids or not set(staff) <= staff_rows.keys():
            abort(403, "В заявке могут быть только участники своей команды")
        conn.execute("DELETE FROM match_lineups WHERE match_id=? AND team_id=?", (match_id, team))
        conn.execute("DELETE FROM match_staff WHERE match_id=? AND team_id=?", (match_id, team))
        for player in starters + bench:
            conn.execute(
                "INSERT INTO match_lineups (match_id,player_id,team_id,is_starter,is_goalkeeper,is_captain,minute_in,minute_out,minutes_played) VALUES (?,?,?,?,?,?,0,90,0)",
                (
                    match_id,
                    player,
                    team,
                    int(player in starters),
                    int(player in keepers or player_rows[player]["position"] == "GK"),
                    int(player in captains),
                ),
            )
        for member in staff:
            conn.execute(
                "INSERT INTO match_staff (match_id,staff_id,team_id,role) VALUES (?,?,?,?)",
                (match_id, member, team, staff_rows[member]["role"]),
            )
        validate_team_lineup(conn, match_id, team)
        calculate_minutes(conn, match_id)
        validate_staff_events(conn, match_id)
        conn.execute(
            "INSERT INTO match_team_submissions (match_id,team_id,status) VALUES (?,?,'DRAFT') ON CONFLICT(match_id,team_id) DO UPDATE SET status='DRAFT',checked_by=NULL",
            (match_id, team),
        )
        conn.execute("UPDATE matches SET status='DRAFT' WHERE id=?", (match_id,))
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/submit-lineup")
@roles_required("team_admin", "organizer")
def submit_lineup(match_id):
    with db_connection(write=True) as conn:
        match, team = team_match(conn, match_id)
        validate_team_lineup(conn, match_id, team)
        conn.execute(
            "UPDATE match_team_submissions SET status='SUBMITTED' WHERE match_id=? AND team_id=?",
            (match_id, team),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/check-lineup/<int:team_id>")
@roles_required("referee", "organizer")
def check_lineup(match_id, team_id):
    with db_connection(write=True) as conn:
        match = require_referee(conn, match_id, approved=False)
        if team_id not in (match["home_team_id"], match["away_team_id"]):
            abort(400)
        row = conn.execute(
            "SELECT status FROM match_team_submissions WHERE match_id=? AND team_id=?",
            (match_id, team_id),
        ).fetchone()
        if not row or row["status"] != "SUBMITTED":
            abort(409, "Команда должна сначала отправить заявку")
        validate_team_lineup(conn, match_id, team_id)
        conn.execute(
            "UPDATE match_team_submissions SET status='APPROVED',checked_by=? WHERE match_id=? AND team_id=?",
            (g.user["username"], match_id, team_id),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/return-lineup/<int:team_id>")
@roles_required("referee", "organizer")
def return_lineup(match_id, team_id):
    with db_connection(write=True) as conn:
        match = require_referee(conn, match_id, approved=False)
        if team_id not in (match["home_team_id"], match["away_team_id"]):
            abort(400)
        if has_match_events(conn, match_id):
            abort(409, "Сначала удалите события и замены матча")
        conn.execute(
            "UPDATE match_team_submissions SET status='DRAFT',checked_by=NULL WHERE match_id=? AND team_id=?",
            (match_id, team_id),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/teams/<int:team_id>/staff")
@roles_required("team_admin", "organizer")
def add_staff(team_id):
    if g.user["role"] != "organizer" and team_id != g.user["team_id"]:
        abort(403)
    fields = {
        name: request.form.get(name, "").strip()
        for name in ("first_name", "last_name", "role", "nationality")
    }
    if any(not value or len(value) > 100 for value in fields.values()):
        abort(400, "Заполните имя, фамилию, роль и гражданство (до 100 символов)")
    with db_connection(write=True) as conn:
        conn.execute(
            "INSERT INTO staff (team_id,first_name,last_name,role,nationality) VALUES (?,?,?,?,?)",
            (
                team_id,
                fields["first_name"],
                fields["last_name"],
                fields["role"],
                fields["nationality"],
            ),
        )
    return redirect(url_for("public.team_detail", team_id=team_id))
