"""Shared form parsing and match access checks for HTTP handlers."""

from datetime import datetime
from flask import abort, g, request
from premier_league.services.protocol import form_int, match_row


def match_date_value():
    value = request.form.get("match_date", "").strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        abort(400, "Укажите дату и время матча")
    if parsed.tzinfo is not None:
        abort(400, "Укажите местное время без часового пояса")
    return parsed.isoformat(timespec="minutes")


def referee_id_value(conn):
    referee_id = form_int("referee_user_id")
    if not conn.execute(
        "SELECT 1 FROM users WHERE id=? AND role='referee'", (referee_id,)
    ).fetchone():
        abort(400, "Выберите учётную запись судьи")
    return referee_id


def team_match(conn, match_id):
    match = match_row(conn, match_id, editable=True)
    organizer = g.user["role"] == "organizer"
    team = form_int("team_id") if organizer else g.user["team_id"]
    if team not in (match["home_team_id"], match["away_team_id"]):
        abort(403, "Это не матч вашей команды")
    submission = conn.execute(
        "SELECT status FROM match_team_submissions WHERE match_id=? AND team_id=?", (match_id, team)
    ).fetchone()
    if not organizer and submission and submission["status"] != "DRAFT":
        abort(409, "Заявка уже отправлена: судья должен вернуть её на доработку")
    if not organizer and has_match_events(conn, match_id):
        abort(409, "Матч уже имеет события; составы зафиксированы")
    return match, team


def has_match_events(conn, match_id):
    return any(
        conn.execute(f"SELECT 1 FROM {table} WHERE match_id=?", (match_id,)).fetchone()
        for table in ("match_events", "match_substitutions", "staff_events")
    )


def selected_ids(name):
    try:
        values = [int(x) for x in request.form.getlist(name) if x.strip()]
    except ValueError:
        abort(400, "Некорректный список участников")
    if len(values) != len(set(values)):
        abort(400, "Участник выбран дважды")
    return values
