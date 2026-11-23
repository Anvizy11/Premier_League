"""Create players and staff within the editor's authorized club."""

import sqlite3

from flask import Blueprint, abort, g, redirect, request, url_for

from premier_league.auth import roles_required
from premier_league.database import db_connection
from premier_league.services.people import check_person_unique, person_fields
from premier_league.services.protocol import form_int

bp = Blueprint("people", __name__)


def require_team_editor(conn, team_id):
    if g.user["role"] != "organizer" and team_id != g.user["team_id"]:
        abort(403)
    if not conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone():
        abort(404)


@bp.post("/teams/<int:team_id>/players")
@roles_required("team_admin", "organizer")
def add_player(team_id):
    with db_connection(write=True) as conn:
        require_team_editor(conn, team_id)
        fields = person_fields(request.form)
        position = request.form.get("position", "")
        if position not in ("GK", "DF", "MF", "FW"):
            abort(400, "Выберите позицию игрока")
        number = form_int("jersey_number", maximum=2**63 - 1)
        check_person_unique(conn, "players", fields)
        if conn.execute(
            "SELECT 1 FROM players WHERE team_id=? AND jersey_number=?", (team_id, number)
        ).fetchone():
            abort(409, "Этот игровой номер уже занят в команде")
        try:
            conn.execute(
                """INSERT INTO players
                (team_id,first_name,last_name,birth_date,jersey_number,position,nationality)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    team_id,
                    fields["first_name"],
                    fields["last_name"],
                    fields["birth_date"],
                    number,
                    position,
                    fields["nationality"],
                ),
            )
        except sqlite3.IntegrityError:
            abort(409, "Такой игрок уже существует или его данные недопустимы")
    return redirect(
        url_for("public.team_detail", team_id=team_id, tab="players", _anchor="tab-players")
    )


@bp.post("/teams/<int:team_id>/staff")
@roles_required("team_admin", "organizer")
def add_staff(team_id):
    with db_connection(write=True) as conn:
        require_team_editor(conn, team_id)
        fields = person_fields(request.form)
        role = " ".join(request.form.get("role", "").split())
        if not role or len(role) > 100:
            abort(400, "Укажите роль члена штаба (до 100 символов)")
        check_person_unique(conn, "staff", fields)
        try:
            conn.execute(
                "INSERT INTO staff (team_id,first_name,last_name,birth_date,role,nationality) VALUES (?,?,?,?,?,?)",
                (
                    team_id,
                    fields["first_name"],
                    fields["last_name"],
                    fields["birth_date"],
                    role,
                    fields["nationality"],
                ),
            )
        except sqlite3.IntegrityError:
            abort(409, "Такой член штаба уже существует или его данные недопустимы")
    return redirect(
        url_for("public.team_detail", team_id=team_id, tab="staff", _anchor="tab-staff")
    )
