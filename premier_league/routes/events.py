"""Events routes."""

from flask import Blueprint, abort, request, redirect, url_for
from premier_league.database import db_connection
from premier_league.auth import roles_required
from premier_league.services.protocol import (
    validate_lineups,
    calculate_minutes,
    form_int,
    require_referee,
    validate_staff_events,
)

bp = Blueprint("events", __name__)


@bp.post("/matches/<int:match_id>/add-event")
@roles_required("referee", "organizer")
def add_match_event(match_id):
    player_id, minute = form_int("player_id"), form_int("minute", 1, 90)
    kind = request.form.get("event_type")
    if kind not in ("GOAL", "PENALTY", "OWN_GOAL", "YELLOW_CARD", "RED_CARD"):
        abort(400, "Неизвестное событие")
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        validate_lineups(conn, match_id)
        player = conn.execute(
            "SELECT team_id FROM match_lineups WHERE match_id=? AND player_id=?",
            (match_id, player_id),
        ).fetchone()
        if not player:
            abort(400, "Игрок отсутствует в заявке")
        conn.execute(
            "INSERT INTO match_events (match_id,team_id,player_id,event_type,minute) VALUES (?,?,?,?,?)",
            (match_id, player["team_id"], player_id, kind, minute),
        )
        calculate_minutes(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/staff-event")
@roles_required("referee", "organizer")
def add_staff_event(match_id):
    member, minute = form_int("staff_id"), form_int("minute", 1, 90)
    kind = request.form.get("event_type")
    if kind not in ("YELLOW_CARD", "RED_CARD"):
        abort(400)
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        validate_lineups(conn, match_id)
        staff = conn.execute(
            "SELECT team_id FROM match_staff WHERE match_id=? AND staff_id=?", (match_id, member)
        ).fetchone()
        if not staff:
            abort(400, "Член штаба отсутствует в заявке")
        conn.execute(
            "INSERT INTO staff_events (match_id,team_id,staff_id,event_type,minute) VALUES (?,?,?,?,?)",
            (match_id, staff["team_id"], member, kind, minute),
        )
        validate_staff_events(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/delete-event/<int:event_id>")
@roles_required("referee", "organizer")
def delete_match_event(match_id, event_id):
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        conn.execute("DELETE FROM match_events WHERE id=? AND match_id=?", (event_id, match_id))
        calculate_minutes(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/delete-staff-event/<int:event_id>")
@roles_required("referee", "organizer")
def delete_staff_event(match_id, event_id):
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        conn.execute("DELETE FROM staff_events WHERE id=? AND match_id=?", (event_id, match_id))
        validate_staff_events(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/make-substitution")
@roles_required("referee", "organizer")
def make_substitution(match_id):
    outgoing, incoming, minute = (
        form_int("player_out_id"),
        form_int("player_in_id"),
        form_int("minute", 1, 90),
    )
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        validate_lineups(conn, match_id)
        if (
            outgoing == incoming
            or conn.execute(
                "SELECT 1 FROM match_substitutions WHERE match_id=? AND (player_out_id=? OR player_in_id=?)",
                (match_id, outgoing, incoming),
            ).fetchone()
        ):
            abort(400, "Некорректная или повторная замена")
        conn.execute(
            "INSERT INTO match_substitutions (match_id,player_out_id,player_in_id,minute) VALUES (?,?,?,?)",
            (match_id, outgoing, incoming, minute),
        )
        calculate_minutes(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/delete-substitution/<int:substitution_id>")
@roles_required("referee", "organizer")
def delete_substitution(match_id, substitution_id):
    with db_connection(write=True) as conn:
        require_referee(conn, match_id)
        conn.execute(
            "DELETE FROM match_substitutions WHERE id=? AND match_id=?", (substitution_id, match_id)
        )
        calculate_minutes(conn, match_id)
    return redirect(url_for("matches.match_protocol", match_id=match_id))
