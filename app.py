from flask import Flask, render_template, abort, request, redirect, url_for
from database import db_connection

app = Flask(__name__)

def get_standings():
    with db_connection() as conn:
        cursor = conn.cursor()

        teams = cursor.execute("SELECT id, name, short_name FROM teams ORDER BY name ASC").fetchall()

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
                "points": 0
            }

        # В таблицу идут ТОЛЬКО утвержденные протоколы (status = 'VERIFIED')
        matches = cursor.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM matches
            WHERE status = 'VERIFIED'
        """).fetchall()

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

        standings_list.sort(key=lambda x: (x["points"], x["gd"], x["gf"], -ord(x["name"][0])), reverse=True)
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
    with db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                p.id, p.first_name, p.last_name, p.is_suspended,
                t.short_name AS team_short_name,
                SUM(CASE WHEN e.event_type = 'YELLOW_CARD' THEN 1 ELSE 0 END) AS yellow_cards,
                SUM(CASE WHEN e.event_type = 'RED_CARD' THEN 1 ELSE 0 END) AS red_cards
            FROM match_events e
            JOIN matches m ON e.match_id = m.id
            JOIN players p ON e.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE e.event_type IN ('YELLOW_CARD', 'RED_CARD') AND m.status = 'VERIFIED'
            GROUP BY p.id
            ORDER BY red_cards DESC, yellow_cards DESC
            LIMIT ?;
        """
        return cursor.execute(query, (limit,)).fetchall()

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

@app.route("/")
def index():
    return render_template(
        "standings.html",
        standings=get_standings(),
        top_scorers=get_top_scorers(limit=None),
        disciplinary_leaders=get_disciplinary_leaders()
    )

@app.route("/teams")
def teams_list():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.id, 
                t.name, 
                t.short_name, 
                t.city, 
                t.stadium,
                s.first_name AS coach_fn,
                s.last_name AS coach_ln,
                s.nationality AS coach_nat,
                COUNT(p.id) AS player_count
            FROM teams t
            LEFT JOIN staff s ON t.id = s.team_id AND s.role = 'Head Coach'
            LEFT JOIN players p ON t.id = p.team_id
            GROUP BY t.id
            ORDER BY t.name ASC
        """)
        teams = cursor.fetchall()
    return render_template("teams.html", teams=teams)


@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        team = cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            abort(404)

        players = cursor.execute("""
            SELECT * FROM players
            WHERE team_id = ?
            ORDER BY
                CASE position
                    WHEN 'GK' THEN 1
                    WHEN 'DF' THEN 2
                    WHEN 'MF' THEN 3
                    WHEN 'FW' THEN 4
                END, jersey_number ASC
        """, (team_id,)).fetchall()

        staff = cursor.execute("SELECT * FROM staff WHERE team_id = ? ORDER BY id ASC", (team_id,)).fetchall()
        return render_template("team_detail.html", team=team, players=players, staff=staff)

@app.route("/players/<int:player_id>")
def player_detail(player_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT p.*, t.name AS team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            WHERE p.id = ?
        """
        player = cursor.execute(query, (player_id,)).fetchone()
        if not player:
            abort(404)

        stats = {"appearances": 0, "goals": 0, "yellow_cards": 0, "red_cards": 0, "minutes": 0}

        # Считаем только из утвержденных матчей
        events = cursor.execute("""
            SELECT e.event_type, COUNT(*) as cnt
            FROM match_events e
            JOIN matches m ON e.match_id = m.id
            WHERE e.player_id = ? AND m.status = 'VERIFIED'
            GROUP BY e.event_type
        """, (player_id,)).fetchall()

        for event in events:
            if event["event_type"] in ("GOAL", "PENALTY"):
                stats["goals"] += event["cnt"]
            elif event["event_type"] == "YELLOW_CARD":
                stats["yellow_cards"] += event["cnt"]
            elif event["event_type"] == "RED_CARD":
                stats["red_cards"] += event["cnt"]

        minutes_row = cursor.execute("""
            SELECT SUM(ml.minutes_played) as total_min, COUNT(ml.id) as apps
            FROM match_lineups ml
            JOIN matches m ON ml.match_id = m.id
            WHERE ml.player_id = ? AND m.status = 'VERIFIED'
        """, (player_id,)).fetchone()

        if minutes_row:
            stats["minutes"] = minutes_row["total_min"] or 0
            stats["appearances"] = minutes_row["apps"] or 0

        return render_template("player_detail.html", player=player, stats=stats)

@app.route("/admin")
def admin_panel():
    with db_connection() as conn:
        cursor = conn.cursor()

        teams = cursor.execute("SELECT id, name FROM teams ORDER BY name ASC").fetchall()

        # Список всех матчей и их статусов
        matches = cursor.execute("""
            SELECT m.*, ht.name as home_name, at.name as away_name
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            ORDER BY m.id DESC
        """).fetchall()

        players = cursor.execute("""
            SELECT p.*, t.name as team_name
            FROM players p
            JOIN teams t ON p.team_id = t.id
            ORDER BY t.name ASC, p.last_name ASC
        """).fetchall()

        return render_template("admin.html", teams=teams, matches=matches, players=players)

@app.route("/admin/create-fixture", methods=["POST"])
def create_fixture():
    home_id = int(request.form.get("home_team_id"))
    away_id = int(request.form.get("away_team_id"))
    gameweek = int(request.form.get("gameweek", 1))

    if home_id != away_id:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO matches (gameweek, home_team_id, away_team_id, home_score, away_score, status, is_finished)
                VALUES (?, ?, ?, 0, 0, 'SCHEDULED', 0)
            """, (gameweek, home_id, away_id))
            match_id = cursor.lastrowid

            # Автоматически создаем начальную заявку: первые 11 игроков в старт, остальные на замену
            for t_id in (home_id, away_id):
                team_players = cursor.execute("SELECT id FROM players WHERE team_id = ? ORDER BY id ASC", (t_id,)).fetchall()
                for idx, p in enumerate(team_players):
                    is_starter = 1 if idx < 11 else 0
                    cursor.execute("""
                        INSERT INTO match_lineups (match_id, player_id, team_id, is_starter, minute_in, minute_out, minutes_played)
                        VALUES (?, ?, ?, ?, 0, 90, 0)
                    """, (match_id, p["id"], t_id, is_starter))

        return redirect(url_for("match_protocol", match_id=match_id))

    return redirect(url_for("admin_panel"))

@app.route("/matches/<int:match_id>/protocol")
def match_protocol(match_id):
    with db_connection() as conn:
        cursor = conn.cursor()

        match = cursor.execute("""
            SELECT m.*, ht.name as home_name, at.name as away_name
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.id = ?
        """, (match_id,)).fetchone()

        if not match:
            abort(404)

        # Игроки с привязкой к заявке матча
        home_players = cursor.execute("""
            SELECT p.*, ml.id as lineup_id, ml.is_starter, ml.minutes_played
            FROM players p
            LEFT JOIN match_lineups ml ON p.id = ml.player_id AND ml.match_id = ?
            WHERE p.team_id = ?
            ORDER BY ml.is_starter DESC, p.jersey_number ASC
        """, (match_id, match["home_team_id"])).fetchall()

        away_players = cursor.execute("""
            SELECT p.*, ml.id as lineup_id, ml.is_starter, ml.minutes_played
            FROM players p
            LEFT JOIN match_lineups ml ON p.id = ml.player_id AND ml.match_id = ?
            WHERE p.team_id = ?
            ORDER BY ml.is_starter DESC, p.jersey_number ASC
        """, (match_id, match["away_team_id"])).fetchall()

        # События
        events = cursor.execute("""
            SELECT e.*, p.first_name, p.last_name, t.short_name as team_short_name
            FROM match_events e
            JOIN players p ON e.player_id = p.id
            JOIN teams t ON p.team_id = t.id
            WHERE e.match_id = ?
            ORDER BY e.minute ASC
        """, (match_id,)).fetchall()

        return render_template("protocol.html", match=match, home_players=home_players, away_players=away_players, events=events)

@app.route("/matches/<int:match_id>/add-event", methods=["POST"])
def add_match_event(match_id):
    player_id = int(request.form.get("player_id"))
    event_type = request.form.get("event_type")
    minute = int(request.form.get("minute", 1))

    with db_connection() as conn:
        cursor = conn.cursor()
        player = cursor.execute("SELECT team_id FROM players WHERE id = ?", (player_id,)).fetchone()
        if not player:
            abort(404)

        cursor.execute("""
            INSERT INTO match_events (match_id, team_id, player_id, event_type, minute)
            VALUES (?, ?, ?, ?, ?)
        """, (match_id, player["team_id"], player_id, event_type, minute))

        # Переводим статус в черновик (DRAFT), если был SCHEDULED
        cursor.execute("""
            UPDATE matches SET status = 'DRAFT' WHERE id = ? AND status = 'SCHEDULED'
        """, (match_id,))

    return redirect(url_for("match_protocol", match_id=match_id))

@app.route("/matches/<int:match_id>/delete-event/<int:event_id>", methods=["POST"])
def delete_match_event(match_id, event_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        match = cursor.execute("SELECT status FROM matches WHERE id = ?", (match_id,)).fetchone()
        if match and match["status"] != 'VERIFIED':
            cursor.execute("DELETE FROM match_events WHERE id = ? AND match_id = ?", (event_id, match_id))

    return redirect(url_for("match_protocol", match_id=match_id))


@app.route("/matches/<int:match_id>/submit-for-review", methods=["POST"])
def submit_for_review(match_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET status = 'PENDING_REVIEW' WHERE id = ?", (match_id,))
    return redirect(url_for("match_protocol", match_id=match_id))


@app.route("/matches/<int:match_id>/verify-protocol", methods=["POST"])
def verify_protocol(match_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        
        match = cursor.execute("SELECT home_team_id, away_team_id FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not match:
            abort(404)

        # 1. Считаем обычные голы хозяев и гостей
        home_goals = cursor.execute("""
            SELECT COUNT(e.id) FROM match_events e
            JOIN players p ON e.player_id = p.id
            WHERE e.match_id = ? AND p.team_id = ? AND e.event_type IN ('GOAL', 'PENALTY')
        """, (match_id, match["home_team_id"])).fetchone()[0]

        away_goals = cursor.execute("""
            SELECT COUNT(e.id) FROM match_events e
            JOIN players p ON e.player_id = p.id
            WHERE e.match_id = ? AND p.team_id = ? AND e.event_type IN ('GOAL', 'PENALTY')
        """, (match_id, match["away_team_id"])).fetchone()[0]

        # 2. Считаем автоголы (срезка игрока своей команды идет в пользу соперника)
        home_own_goals = cursor.execute("""
            SELECT COUNT(e.id) FROM match_events e
            JOIN players p ON e.player_id = p.id
            WHERE e.match_id = ? AND p.team_id = ? AND e.event_type = 'OWN_GOAL'
        """, (match_id, match["home_team_id"])).fetchone()[0]

        away_own_goals = cursor.execute("""
            SELECT COUNT(e.id) FROM match_events e
            JOIN players p ON e.player_id = p.id
            WHERE e.match_id = ? AND p.team_id = ? AND e.event_type = 'OWN_GOAL'
        """, (match_id, match["away_team_id"])).fetchone()[0]

        # Итоговый счет: свои забитые мячи + автоголы соперника
        final_home_score = home_goals + away_own_goals
        final_away_score = away_goals + home_own_goals

        # 3. Рассчитываем минуты сыгранного времени
        cursor.execute("""
            UPDATE match_lineups
            SET minutes_played = CASE WHEN is_starter = 1 THEN 90 ELSE 0 END
            WHERE match_id = ?
        """, (match_id,))

        # Учитываем удаление (минута красной карточки отсекает время на поле)
        red_cards = cursor.execute("""
            SELECT player_id, minute FROM match_events
            WHERE match_id = ? AND event_type = 'RED_CARD'
        """, (match_id,)).fetchall()

        for rc in red_cards:
            cursor.execute("""
                UPDATE match_lineups
                SET minutes_played = ?
                WHERE match_id = ? AND player_id = ?
            """, (rc["minute"], match_id, rc["player_id"]))

        # 4. Фиксируем итоговый счет с автоголами и статус VERIFIED
        cursor.execute("""
            UPDATE matches
            SET home_score = ?, away_score = ?, status = 'VERIFIED', is_finished = 1
            WHERE id = ?
        """, (final_home_score, final_away_score, match_id))

    return redirect(url_for("match_protocol", match_id=match_id))


@app.route("/admin/toggle-suspension/player/<int:player_id>", methods=["POST"])
def toggle_player_suspension(player_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE players
            SET is_suspended = CASE WHEN is_suspended = 1 THEN 0 ELSE 1 END
            WHERE id = ?
        """, (player_id,))
    return redirect(url_for("admin_panel"))


@app.route("/matches/<int:match_id>/reopen-protocol", methods=["POST"])
def reopen_protocol(match_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE matches 
            SET status = 'PENDING_REVIEW', is_finished = 0 
            WHERE id = ?
        """, (match_id,))

    return redirect(url_for("match_protocol", match_id=match_id))


if __name__ == '__main__':
    app.run(debug=True, port=5001)
