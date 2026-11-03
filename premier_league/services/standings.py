"""Standings, scoring and disciplinary leaderboards from verified matches."""

from premier_league.database import db_connection


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


def get_disciplinary_leaders(limit=5):
    from premier_league.services.discipline import disciplinary_state

    with db_connection() as conn:
        state = disciplinary_state(conn)
        players = {}
        for row in conn.execute(
            """SELECT p.*, t.short_name AS team_short_name, e.match_id,
            SUM(e.event_type='YELLOW_CARD') AS yellows, SUM(e.event_type='RED_CARD') AS reds
            FROM players p JOIN teams t ON t.id=p.team_id JOIN match_events e ON e.player_id=p.id
            JOIN matches m ON m.id=e.match_id WHERE m.status='VERIFIED'
            AND e.event_type IN ('YELLOW_CARD','RED_CARD') GROUP BY p.id,e.match_id"""
        ):
            person = players.setdefault(row["id"], dict(row, yellow_cards=0, red_cards=0))
            person["yellow_cards"] += row["yellows"]
            person["red_cards"] += row["reds"] + int(row["yellows"] >= 2)
            person["is_suspended"] = state["player", row["id"]]["blocked"]
        return sorted(
            players.values(), key=lambda p: (-p["red_cards"], -p["yellow_cards"], p["last_name"])
        )[:limit]


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
