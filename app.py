from flask import Flask, render_template, abort
from database import get_connection

app = Flask(__name__)

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

    stats = {
        "appearances": 0,
        "goals": 0,
        "yellow_cards": 0,
        "red_cards": 0
    }

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

@app.route("/suspensions")
def suspensions_list():
    conn = get_connection()
    cursor = conn.cursor()

    suspended_players = cursor.execute("""
        SELECT p.*, t.name AS team_name 
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.is_suspended = 1
        ORDER BY t.name ASC, p.last_name ASC
    """).fetchall()

    suspended_staff = cursor.execute("""
        SELECT s.*, t.name AS team_name 
        FROM staff s
        JOIN teams t ON s.team_id = t.id
        WHERE s.is_suspended = 1
        ORDER BY t.name ASC, s.last_name ASC
    """).fetchall()

    conn.close()
    return render_template(
        "suspensions.html", 
        suspended_players=suspended_players, 
        suspended_staff=suspended_staff
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
