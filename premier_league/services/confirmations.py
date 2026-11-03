"""Confirmations refer to the exact protocol content, not only its status."""

import hashlib
import json


def protocol_hash(conn, match_id):
    match = conn.execute(
        """SELECT id,home_team_id,away_team_id,gameweek,match_date,
        referee_user_id,referee_name,assistant_one,assistant_two,fourth_official,var_official,avar_official
        FROM matches WHERE id=?""",
        (match_id,),
    ).fetchone()
    content = {"match": dict(match)}
    for table, fields, order in [
        ("match_lineups", "player_id,team_id,is_starter,is_captain,is_goalkeeper", "player_id"),
        ("match_staff", "staff_id,team_id,role", "staff_id"),
        ("match_events", "player_id,team_id,event_type,minute", "minute,id"),
        ("staff_events", "staff_id,team_id,event_type,minute", "minute,id"),
        ("match_substitutions", "player_out_id,player_in_id,minute", "minute,id"),
    ]:
        content[table] = [
            dict(r)
            for r in conn.execute(
                f"SELECT {fields} FROM {table} WHERE match_id=? ORDER BY {order}", (match_id,)
            )
        ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def confirmation_status(conn, match):
    digest = protocol_hash(conn, match["id"])
    saved = {
        r["scope"]: dict(r)
        for r in conn.execute(
            """SELECT c.*,u.username FROM protocol_confirmations c
        JOIN users u ON u.id=c.confirmed_by WHERE c.match_id=?""",
            (match["id"],),
        )
    }
    results = []
    for scope, label in [
        (f"team:{match['home_team_id']}", "Команда хозяев"),
        (f"team:{match['away_team_id']}", "Команда гостей"),
        ("referee", "Назначенный судья"),
    ]:
        row = saved.get(scope)
        valid = bool(row and row["content_hash"] == digest)
        if scope == "referee" and row and row["confirmed_by"] != match["referee_user_id"]:
            valid = False
        results.append(dict(scope=scope, label=label, valid=valid, record=row))
    return results
