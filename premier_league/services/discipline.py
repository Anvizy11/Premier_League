"""Disciplinary state derived from verified matches; no destructive card resets."""

from collections import Counter, defaultdict
from flask import abort


def order_key(match):
    # Legacy games without a recorded date precede newly dated games.
    return (match["match_date"] or "", match["gameweek"], match["id"])


def disciplinary_state(conn, before_match=None):
    """Return card accumulation and bans, optionally immediately before a match.

    Bans run concurrently. Only an absence from the whole match roster serves a
    game. Double-yellow games contribute zero towards the five-game threshold.
    """
    people = {}
    for kind, table in [("player", "players"), ("staff", "staff")]:
        for p in conn.execute(f"SELECT * FROM {table}"):
            people[kind, p["id"]] = dict(person=dict(p), yellow_matches=0, bans=[])
    matches = conn.execute("SELECT * FROM matches WHERE status='VERIFIED'").fetchall()
    timeline = [(order_key(m), 0, m["id"], "match", m) for m in matches]
    for decision in conn.execute("SELECT * FROM disciplinary_decision_history"):
        cutoff = conn.execute(
            "SELECT * FROM matches WHERE id=?", (decision["effective_after_match_id"],)
        ).fetchone()
        timeline.append((order_key(cutoff), 1, decision["id"], "decision", decision))
    for key, _, _, action, match in sorted(timeline, key=lambda item: item[:3]):
        if before_match is not None and key >= order_key(before_match):
            continue
        if action == "decision":
            state = people.get((match["subject_type"], match["subject_id"]))
            if state:
                for ban in state["bans"]:
                    if ban["match_id"] == match["match_id"] and ban["reason"] == match["reason"]:
                        ban.update(
                            total_games=match["total_games"],
                            remaining=max(0, match["total_games"] - match["served_games"]),
                            explanation=match["explanation"],
                        )
            continue
        if before_match is not None and order_key(match) >= order_key(before_match):
            continue
        teams = (match["home_team_id"], match["away_team_id"])
        roster = {
            ("player", r["player_id"])
            for r in conn.execute(
                "SELECT player_id FROM match_lineups WHERE match_id=?", (match["id"],)
            )
        }
        roster |= {
            ("staff", r["staff_id"])
            for r in conn.execute(
                "SELECT staff_id FROM match_staff WHERE match_id=?", (match["id"],)
            )
        }
        for key, state in people.items():
            if state["person"]["team_id"] in teams and key not in roster:
                for ban in state["bans"]:
                    if ban["remaining"]:
                        ban["remaining"] -= 1
        events = defaultdict(Counter)
        for kind, table, field in [
            ("player", "match_events", "player_id"),
            ("staff", "staff_events", "staff_id"),
        ]:
            for e in conn.execute(f"SELECT * FROM {table} WHERE match_id=?", (match["id"],)):
                events[kind, e[field]][e["event_type"]] += 1
        for key, counts in events.items():
            if key not in people:
                continue
            state = people[key]
            reasons = []
            if counts["YELLOW_CARD"] >= 2:
                reasons.append("SECOND_YELLOW")
            elif counts["YELLOW_CARD"] == 1:
                state["yellow_matches"] += 1
                if state["yellow_matches"] % 5 == 0:
                    reasons.append("YELLOW_LIMIT")
            if counts["RED_CARD"]:
                reasons.append("RED_CARD")
            for reason in reasons:
                state["bans"].append(
                    dict(
                        match_id=match["id"],
                        reason=reason,
                        total_games=1,
                        remaining=1,
                        explanation="Автоматическое отстранение",
                    )
                )
    for state in people.values():
        state["remaining"] = max((b["remaining"] for b in state["bans"]), default=0)
        state["blocked"] = bool(state["remaining"] or state["person"]["is_suspended"])
    return people


def check_eligible(conn, match, kind, ids):
    state = disciplinary_state(conn, before_match=match)
    for subject in ids:
        person = state.get((kind, subject))
        if not person or person["blocked"]:
            abort(400, "В заявку включён дисквалифицированный участник")


def assert_no_new_roster_conflicts(conn, previous_conflicts):
    conflicts = roster_conflicts(conn)
    if conflicts - previous_conflicts:
        match_id, _, _ = sorted(conflicts - previous_conflicts)[0]
        abort(
            409,
            f"Изменение делает заявку утверждённого матча #{match_id} недопустимой. Сначала верните этот протокол судье.",
        )


def roster_conflicts(conn):
    """Find historical roster entries that violate an automatic suspension."""
    conflicts = set()
    for match in conn.execute("SELECT * FROM matches WHERE status='VERIFIED'").fetchall():
        state = disciplinary_state(conn, before_match=match)
        for kind, table, field in [
            ("player", "match_lineups", "player_id"),
            ("staff", "match_staff", "staff_id"),
        ]:
            for row in conn.execute(
                f"SELECT {field} FROM {table} WHERE match_id=?", (match["id"],)
            ):
                if state.get((kind, row[field]), {}).get("remaining", 0):
                    conflicts.add((match["id"], kind, row[field]))
    return conflicts
