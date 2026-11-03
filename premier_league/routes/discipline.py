"""Discipline routes."""

from flask import Blueprint, abort, request, redirect, url_for, g
from premier_league.database import db_connection
from premier_league.auth import roles_required
from premier_league.services.protocol import form_int

bp = Blueprint("discipline", __name__)


@bp.post("/discipline/decision")
@roles_required("organizer")
def disciplinary_decision():
    from premier_league.services.discipline import disciplinary_state, order_key

    match_id, subject, total = (
        form_int("match_id"),
        form_int("subject_id"),
        form_int("total_games", 1, 1000),
    )
    kind, reason = request.form.get("subject_type"), request.form.get("reason")
    explanation = request.form.get("explanation", "").strip()
    if not explanation or len(explanation) > 2000:
        abort(400, "Укажите решение КДК (до 2000 символов)")
    with db_connection(write=True) as conn:
        state = disciplinary_state(conn).get((kind, subject))
        ban = (
            next(
                (b for b in state["bans"] if b["match_id"] == match_id and b["reason"] == reason),
                None,
            )
            if state
            else None
        )
        if not ban:
            abort(400, "Санкция не найдена в утверждённых протоколах")
        cutoff = max(
            conn.execute(
                "SELECT * FROM matches WHERE status='VERIFIED' AND (home_team_id=? OR away_team_id=?)",
                (state["person"]["team_id"], state["person"]["team_id"]),
            ),
            key=order_key,
        )
        served = ban["total_games"] - ban["remaining"]
        conn.execute(
            """INSERT INTO disciplinary_decision_history
            (match_id,subject_type,subject_id,reason,total_games,served_games,effective_after_match_id,explanation,decided_by)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                match_id,
                kind,
                subject,
                reason,
                total,
                served,
                cutoff["id"],
                explanation,
                g.user["username"],
            ),
        )
        conn.execute(
            """INSERT INTO disciplinary_decisions (match_id,subject_type,subject_id,reason,total_games,explanation,decided_by)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(match_id,subject_type,subject_id,reason) DO UPDATE SET
            total_games=excluded.total_games,explanation=excluded.explanation,decided_by=excluded.decided_by""",
            (match_id, kind, subject, reason, total, explanation, g.user["username"]),
        )
    return redirect(url_for("admin.admin_panel"))
