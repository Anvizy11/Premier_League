from flask import Flask, render_template
from database import get_connection

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("teams.html", teams=get_teams_summary())

@app.route("/teams")
def teams_list():
    return render_template("teams.html", teams=get_teams_summary())

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

if __name__ == "__main__":
    app.run(debug=True, port=5000)
