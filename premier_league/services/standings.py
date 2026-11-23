"""Standings, scoring and disciplinary leaderboards from verified matches."""

from premier_league.database import db_connection
from premier_league.services.cards import get_card_statistics


def get_standings():
    with db_connection() as conn:
        cursor = conn.cursor()

        teams = cursor.execute(
            "SELECT id, name, short_name FROM teams ORDER BY name ASC"
        ).fetchall()

        table = {}
        for t in teams:
            table[t["id"]] = {
                "id": t["id"],
                "name": t["name"],
                "short_name": t["short_name"],
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "gf": 0,
                "ga": 0,
                "gd": 0,
                "points": 0,
                "red_cards": 0,
                "yellow_cards": 0,
            }

        # В таблицу идут ТОЛЬКО утвержденные протоколы (status = 'VERIFIED')
        matches = cursor.execute(
            """
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM matches
            WHERE status = 'VERIFIED'
        """
        ).fetchall()

        for m in matches:
            h_id = m["home_team_id"]
            a_id = m["away_team_id"]
            h_s = m["home_score"]
            a_s = m["away_score"]

            if h_id in table and a_id in table:
                table[h_id]["played"] += 1
                table[a_id]["played"] += 1
                table[h_id]["gf"] += h_s
                table[h_id]["ga"] += a_s
                table[a_id]["gf"] += a_s
                table[a_id]["ga"] += h_s

                if h_s > a_s:
                    table[h_id]["won"] += 1
                    table[h_id]["points"] += 3
                    table[a_id]["lost"] += 1
                elif h_s < a_s:
                    table[a_id]["won"] += 1
                    table[a_id]["points"] += 3
                    table[h_id]["lost"] += 1
                else:
                    table[h_id]["drawn"] += 1
                    table[h_id]["points"] += 1
                    table[a_id]["drawn"] += 1
                    table[a_id]["points"] += 1

        cards = get_card_statistics(conn)
        for team_id, totals in cards["team"].items():
            if team_id in table:
                table[team_id].update(totals)

        standings_list = list(table.values())
        for item in standings_list:
            item["gd"] = item["gf"] - item["ga"]

        standings_list.sort(
            key=lambda x: (x["points"], x["gd"], x["gf"], -ord(x["name"][0])), reverse=True
        )
        return standings_list


def get_top_scorers(limit=None):
    with db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                p.id, p.first_name, p.last_name, p.jersey_number,
                t.short_name AS team_short_name, t.name AS team_name,
                COUNT(e.id) AS goals
            FROM match_events e
            JOIN matches m ON e.match_id = m.id
            JOIN players p ON e.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE e.event_type IN ('GOAL', 'PENALTY') AND m.status = 'VERIFIED'
            GROUP BY p.id
            ORDER BY goals DESC, p.last_name ASC
        """
        if limit:
            query += " LIMIT ?"
            return cursor.execute(query, (limit,)).fetchall()

        return cursor.execute(query).fetchall()


def get_disciplinary_registry():
    from premier_league.services.discipline import disciplinary_state

    with db_connection() as conn:
        cards = get_card_statistics(conn)
        state = disciplinary_state(conn)
        teams = {row["id"]: row for row in conn.execute("SELECT id,name,short_name FROM teams")}
        registry = []
        for (kind, subject_id), discipline in state.items():
            totals = cards[kind].get(subject_id, {"yellow_cards": 0, "red_cards": 0})
            if not any(totals.values()) and not discipline["blocked"] and not discipline["bans"]:
                continue
            person = discipline["person"]
            team = teams[person["team_id"]]
            registry.append(
                dict(
                    person,
                    **totals,
                    subject_type=kind,
                    team_name=team["name"],
                    team_short_name=team["short_name"],
                    is_suspended=discipline["blocked"],
                    remaining=discipline["remaining"],
                    yellow_matches=discipline["yellow_matches"],
                    suspension_count=len(discipline["bans"]),
                )
            )
        return sorted(
            registry,
            key=lambda p: (
                -p["red_cards"],
                -p["yellow_cards"],
                p["last_name"],
                p["first_name"],
                p["subject_type"],
                p["id"],
            ),
        )


def get_disciplinary_leaders(limit=5):
    players = [
        item
        for item in get_disciplinary_registry()
        if item["subject_type"] == "player" and (item["yellow_cards"] or item["red_cards"])
    ]
    return players if limit is None else players[:limit]


def get_teams_summary():
    with db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                t.id, t.name, t.short_name, t.stadium, t.city,
                s.first_name AS coach_fn, s.last_name AS coach_ln,
                COUNT(p.id) AS player_count
            FROM teams t
            LEFT JOIN staff s ON t.id = s.team_id AND s.role = 'Head Coach'
            LEFT JOIN players p ON t.id = p.team_id
            GROUP BY t.id
            ORDER BY t.name ASC;
        """
        return cursor.execute(query).fetchall()
