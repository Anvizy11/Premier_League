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

    # Получаем информацию о команде
    team = cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team:
        conn.close()
        abort(404)

    # Список игроков с сортировкой по позиции
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

    # Список персонала
    staff = cursor.execute("SELECT * FROM staff WHERE team_id = ? ORDER BY id ASC", (team_id,)).fetchall()

    conn.close()
    return render_template("team_detail.html", team=team, players=players, staff=staff)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
