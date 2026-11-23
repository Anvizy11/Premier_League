"""Matches routes."""

from flask import Blueprint, render_template, abort, request, redirect, url_for, g
from premier_league.database import db_connection
from premier_league.auth import roles_required
from premier_league.services.timeline import build_match_timeline, get_recorded_order
from premier_league.services.protocol import (
    match_row,
    validate_lineups,
    calculate_minutes,
    require_referee,
    validate_staff_events,
    lineups_ready,
    is_foreign,
    canonical_role,
    event_field_positions,
)

bp = Blueprint("matches", __name__)


@bp.route("/matches/<int:match_id>/protocol")
def match_protocol(match_id):
    from premier_league.services.discipline import disciplinary_state

    with db_connection() as conn:
        match = conn.execute(
            """SELECT m.*, h.name AS home_name,a.name AS away_name FROM matches m
            JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id WHERE m.id=?""",
            (match_id,),
        ).fetchone()
        if not match:
            abort(404)
        if match["status"] != "VERIFIED":
            if not g.user:
                return redirect(url_for("auth.login"))
            if g.user["role"] == "team_admin" and g.user["team_id"] not in (
                match["home_team_id"],
                match["away_team_id"],
            ):
                abort(403)
            if g.user["role"] == "referee" and match["referee_user_id"] != g.user["id"]:
                abort(403)
        state = disciplinary_state(conn, before_match=match)
        panels = []
        for team_id, name in [
            (match["home_team_id"], match["home_name"]),
            (match["away_team_id"], match["away_name"]),
        ]:
            players = conn.execute(
                """SELECT p.*,ml.id AS lineup_id,ml.is_starter,ml.minutes_played,ml.is_captain,COALESCE(ml.is_goalkeeper,p.position='GK') AS is_goalkeeper
                FROM players p LEFT JOIN match_lineups ml ON ml.player_id=p.id AND ml.match_id=?
                WHERE p.team_id=? ORDER BY p.jersey_number,p.id""",
                (match_id, team_id),
            ).fetchall()
            staff = conn.execute(
                """SELECT s.*,ms.staff_id AS selected,ms.role AS match_role FROM staff s
                LEFT JOIN match_staff ms ON ms.staff_id=s.id AND ms.match_id=? WHERE s.team_id=? ORDER BY s.id""",
                (match_id, team_id),
            ).fetchall()
            submission = conn.execute(
                "SELECT * FROM match_team_submissions WHERE match_id=? AND team_id=?",
                (match_id, team_id),
            ).fetchone()
            players = [
                dict(
                    p,
                    is_foreign=is_foreign(p["nationality"]),
                    blocked=state["player", p["id"]]["blocked"],
                )
                for p in players
            ]
            staff = sorted(
                [
                    dict(
                        s,
                        is_head_coach=canonical_role(s["match_role"] or s["role"]) == "head_coach",
                    )
                    for s in staff
                ],
                key=lambda s: (
                    canonical_role(s["match_role"] or s["role"]) != "head_coach",
                    s["id"],
                ),
            )
            starters = [p for p in players if p["lineup_id"] and p["is_starter"]]
            bench = [p for p in players if p["lineup_id"] and not p["is_starter"]]
            panels.append(
                dict(
                    id=team_id,
                    name=name,
                    players=players,
                    staff=staff,
                    starters=starters,
                    bench=bench,
                    status=submission["status"] if submission else "DRAFT",
                )
            )
        events = conn.execute(
            """SELECT e.*,p.first_name,p.last_name FROM match_events e JOIN players p ON p.id=e.player_id
            WHERE match_id=? ORDER BY minute,e.id""",
            (match_id,),
        ).fetchall()
        staff_events = conn.execute(
            """SELECT e.*,s.first_name,s.last_name FROM staff_events e JOIN staff s ON s.id=e.staff_id
            WHERE match_id=? ORDER BY minute,e.id""",
            (match_id,),
        ).fetchall()
        substitutions = conn.execute(
            """SELECT ms.*,po.last_name AS out_name,pi.last_name AS in_name FROM match_substitutions ms
            JOIN players po ON po.id=ms.player_out_id JOIN players pi ON pi.id=ms.player_in_id WHERE match_id=? ORDER BY minute,ms.id""",
            (match_id,),
        ).fetchall()
        recorded_order = get_recorded_order(conn, match_id)
        events = [dict(e, recorded_order=recorded_order["player", e["id"]]) for e in events]
        substitutions = [
            dict(s, recorded_order=recorded_order["substitution", s["id"]]) for s in substitutions
        ]
        starters = [p["id"] for panel in panels for p in panel["starters"]]
        field_positions = event_field_positions(starters, substitutions, events)
        events = [dict(e, off_field=not field_positions[e["id"]]) for e in events]
        timeline = build_match_timeline(conn, match_id, events, staff_events, substitutions)
        event_context = dict(
            starters=starters, substitutions=[dict(s) for s in substitutions], events=events
        )
        referees = conn.execute("SELECT id,username FROM users WHERE role='referee'").fetchall()
        is_referee = bool(
            g.user and g.user["role"] == "referee" and match["referee_user_id"] == g.user["id"]
        )
        editable = match["status"] in ("SCHEDULED", "DRAFT")
        is_organizer = bool(g.user and g.user["role"] == "organizer")
        ready = lineups_ready(conn, match_id) and all(
            match[field]
            for field in ("referee_name", "assistant_one", "assistant_two", "fourth_official")
        )
        event_editable = (
            editable
            and ready
            and (is_organizer or (is_referee and all(p["status"] == "APPROVED" for p in panels)))
        )
        from premier_league.services.confirmations import confirmation_status, protocol_hash

        confirmations = confirmation_status(conn, match)
        content_hash = protocol_hash(conn, match_id)
        officials = conn.execute("SELECT name FROM officials ORDER BY name").fetchall()
        return render_template(
            "protocol.html",
            match=match,
            panels=panels,
            discipline=state,
            events=events,
            staff_events=staff_events,
            substitutions=substitutions,
            timeline=timeline,
            referees=referees,
            is_referee=is_referee,
            is_organizer=is_organizer,
            confirmations=confirmations,
            content_hash=content_hash,
            officials=officials,
            event_context=event_context,
            editable=editable,
            event_editable=event_editable,
        )


@bp.post("/matches/<int:match_id>/officials")
@roles_required("referee", "organizer")
def save_officials(match_id):
    required = ("referee_name", "assistant_one", "assistant_two", "fourth_official")
    optional = ("var_official", "avar_official")
    fields = {name: request.form.get(name, "").strip() for name in required + optional}
    if any(not fields[name] for name in required) or any(
        len(value) > 150 for value in fields.values()
    ):
        abort(400, "Заполните четырёх обязательных судей")
    with db_connection(write=True) as conn:
        require_referee(conn, match_id, approved=False)
        known = {row["name"] for row in conn.execute("SELECT name FROM officials")}
        if any(value and value not in known for value in fields.values()):
            abort(400, "Выберите судей из справочника")
        conn.execute(
            "UPDATE matches SET referee_name=?,assistant_one=?,assistant_two=?,fourth_official=?,var_official=?,avar_official=? WHERE id=?",
            (*fields.values(), match_id),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/submit-for-review")
@roles_required("referee", "organizer")
def submit_for_review(match_id):
    with db_connection(write=True) as conn:
        match = require_referee(conn, match_id)
        if not match["match_date"]:
            abort(400, "Организатор должен указать дату и время матча")
        validate_lineups(conn, match_id)
        calculate_minutes(conn, match_id)
        validate_staff_events(conn, match_id)
        conn.execute("UPDATE matches SET status='PENDING_REVIEW' WHERE id=?", (match_id,))
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/verify-protocol")
@roles_required("organizer")
def verify_protocol(match_id):
    from premier_league.services.discipline import roster_conflicts, assert_no_new_roster_conflicts

    with db_connection(write=True) as conn:
        previous_conflicts = roster_conflicts(conn)
        match = match_row(conn, match_id)
        if match["status"] != "PENDING_REVIEW":
            abort(409, "Судья должен отправить протокол на проверку")
        if (
            not match["match_date"]
            or not match["referee_user_id"]
            or not all(
                match[field]
                for field in ("referee_name", "assistant_one", "assistant_two", "fourth_official")
            )
        ):
            abort(400, "Не заполнены назначение, дата или судейская бригада")
        # Participant confirmations are separate from organizer approval.
        validate_lineups(conn, match_id)
        calculate_minutes(conn, match_id)
        validate_staff_events(conn, match_id)
        home = away = 0
        for event in conn.execute("SELECT * FROM match_events WHERE match_id=?", (match_id,)):
            if event["event_type"] in ("GOAL", "PENALTY", "OWN_GOAL"):
                is_home = event["team_id"] == match["home_team_id"]
                if event["event_type"] == "OWN_GOAL":
                    is_home = not is_home
                if is_home:
                    home += 1
                else:
                    away += 1
        conn.execute(
            "UPDATE matches SET home_score=?,away_score=?,status='VERIFIED',is_finished=1,verified_by=? WHERE id=?",
            (home, away, g.user["username"], match_id),
        )
        assert_no_new_roster_conflicts(conn, previous_conflicts)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/reopen-protocol")
@roles_required("organizer")
def reopen_protocol(match_id):
    from premier_league.services.discipline import roster_conflicts, assert_no_new_roster_conflicts

    with db_connection(write=True) as conn:
        previous_conflicts = roster_conflicts(conn)
        match = match_row(conn, match_id)
        if match["status"] not in ("VERIFIED", "PENDING_REVIEW"):
            abort(409, "Протокол не находится на проверке")
        conn.execute(
            "UPDATE matches SET status='DRAFT',is_finished=0,verified_by=NULL WHERE id=?",
            (match_id,),
        )
        assert_no_new_roster_conflicts(conn, previous_conflicts)
    return redirect(url_for("matches.match_protocol", match_id=match_id))


@bp.post("/matches/<int:match_id>/confirm")
@roles_required("team_admin", "referee")
def confirm_protocol(match_id):
    from premier_league.services.confirmations import protocol_hash

    with db_connection(write=True) as conn:
        match = match_row(conn, match_id)
        if match["status"] not in ("PENDING_REVIEW", "VERIFIED"):
            abort(409, "Подтверждение доступно для готового итогового протокола")
        if g.user["role"] == "team_admin":
            if g.user["team_id"] not in (match["home_team_id"], match["away_team_id"]):
                abort(403)
            scope = f"team:{g.user['team_id']}"
        else:
            if match["referee_user_id"] != g.user["id"]:
                abort(403)
            scope = "referee"
        digest = protocol_hash(conn, match_id)
        if request.form.get("content_hash") != digest:
            abort(409, "Протокол изменился. Обновите страницу и проверьте его заново")
        conn.execute(
            """INSERT INTO protocol_confirmations (match_id,scope,confirmed_by,content_hash)
            VALUES (?,?,?,?) ON CONFLICT(match_id,scope) DO UPDATE SET confirmed_by=excluded.confirmed_by,
            content_hash=excluded.content_hash,confirmed_at=CURRENT_TIMESTAMP""",
            (match_id, scope, g.user["id"], digest),
        )
    return redirect(url_for("matches.match_protocol", match_id=match_id))
