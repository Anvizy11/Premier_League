from flask import Flask, render_template, abort, request, redirect, url_for
from database import get_connection

app = Flask(__name__)

def get_standings():
    conn = get_connection()
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

    matches = cursor.execute("""
        SELECT home_team_id, away_team_id, home_score, away_score 
        FROM matches 
        WHERE is_finished = 1
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
    conn.close()
    return standings_list

def get_top_scorers(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT 
            p.id, p.first_name, p.last_name, p.jersey_number,
            t.short_name AS team_short_name, t.name AS team_name,
            COUNT(e.id) AS goals
        FROM match_events e
        JOIN players p ON e.player_id = p.id
        JOIN teams t ON p.team_id = t.id
        WHERE e.event_type IN ('GOAL', 'PENALTY')
        GROUP BY p.id
        ORDER BY goals DESC, p.last_name ASC
        LIMIT ?;
    """
    scorers = cursor.execute(query, (limit,)).fetchall()
    conn.close()
    return scorers

def get_disciplinary_leaders(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT 
            p.id, p.first_name, p.last_name, p.is_suspended,
            t.short_name AS team_short_name,
            SUM(CASE WHEN e.event_type = 'YELLOW_CARD' THEN 1 ELSE 0 END) AS yellow_cards,
            SUM(CASE WHEN e.event_type = 'RED_CARD' THEN 1 ELSE 0 END) AS red_cards
        FROM match_events e
        JOIN players p ON e.player_id = p.id
        JOIN teams t ON p.team_id = t.id
        WHERE e.event_type IN ('YELLOW_CARD', 'RED_CARD')
        GROUP BY p.id
        ORDER BY red_cards DESC, yellow_cards DESC
        LIMIT ?;
    """
    leaders = cursor.execute(query, (limit,)).fetchall()
    conn.close()
    return leaders

def get_teams_summary():
    conn = get_connection()
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
    teams = cursor.execute(query).fetchall()
    conn.close()
    return teams

@app.route("/")
def index():
    return render_template(
        "standings.html",
        standings=get_standings(),
        top_scorers=get_top_scorers(),
        disciplinary_leaders=get_disciplinary_leaders()
    )

@app.route("/teams")
def teams_list():
    return render_template("teams.html", teams=get_teams_summary())

@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    conn = get_connection()
    cursor = conn.cursor()

    team = cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team:
        conn.close()
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
    conn.close()
    return render_template("team_detail.html", team=team, players=players, staff=staff)

@app.route("/players/<int:player_id>")
def player_detail(player_id):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.*, t.name AS team_name 
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.id = ?
    """
    player = cursor.execute(query, (player_id,)).fetchone()
    if not player:
        conn.close()
        abort(404)

    stats = {"appearances": 0, "goals": 0, "yellow_cards": 0, "red_cards": 0}
    events = cursor.execute("""
        SELECT event_type, COUNT(*) as cnt 
        FROM match_events 
        WHERE player_id = ? 
        GROUP BY event_type
    """, (player_id,)).fetchall()

    for event in events:
        if event["event_type"] in ("GOAL", "PENALTY"):
            stats["goals"] += event["cnt"]
        elif event["event_type"] == "YELLOW_CARD":
            stats["yellow_cards"] += event["cnt"]
        elif event["event_type"] == "RED_CARD":
            stats["red_cards"] += event["cnt"]

    conn.close()
    return render_template("player_detail.html", player=player, stats=stats)

@app.route("/admin")
def admin_panel():
    conn = get_connection()
    cursor = conn.cursor()

    players = cursor.execute("""
        SELECT p.*, t.name as team_name 
        FROM players p 
        JOIN teams t ON p.team_id = t.id 
        ORDER BY t.name ASC, p.last_name ASC
    """).fetchall()

    staff = cursor.execute("""
        SELECT s.*, t.name as team_name 
        FROM staff s 
        JOIN teams t ON s.team_id = t.id 
        ORDER BY t.name ASC, s.last_name ASC
    """).fetchall()

    conn.close()
    return render_template("admin.html", players=players, staff=staff)

@app.route("/admin/toggle-suspension/player/<int:player_id>", methods=["POST"])
def toggle_player_suspension(player_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE players 
        SET is_suspended = CASE WHEN is_suspended = 1 THEN 0 ELSE 1 END 
        WHERE id = ?
    """, (player_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

@app.route("/admin/toggle-suspension/staff/<int:staff_id>", methods=["POST"])
def toggle_staff_suspension(staff_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE staff 
        SET is_suspended = CASE WHEN is_suspended = 1 THEN 0 ELSE 1 END 
        WHERE id = ?
    """, (staff_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))

if __name__ == "__main__":
    app.run(debug=True, port=5001)
