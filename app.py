from flask import Flask, render_template, abort, request, redirect, url_for, g
from database import db_connection
from auth import configure_auth, roles_required
from protocol_logic import match_row, validate_lineups, calculate_minutes, form_int, validate_team_lineup, require_referee, validate_staff_events, lineups_ready, is_foreign, canonical_role, event_field_positions

app = Flask(__name__)
configure_auth(app)

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
    from discipline import disciplinary_state
    with db_connection() as conn:
        state = disciplinary_state(conn)
        players = {}
        for row in conn.execute("""SELECT p.*, t.short_name AS team_short_name, e.match_id,
            SUM(e.event_type='YELLOW_CARD') AS yellows, SUM(e.event_type='RED_CARD') AS reds
            FROM players p JOIN teams t ON t.id=p.team_id JOIN match_events e ON e.player_id=p.id
            JOIN matches m ON m.id=e.match_id WHERE m.status='VERIFIED'
            AND e.event_type IN ('YELLOW_CARD','RED_CARD') GROUP BY p.id,e.match_id"""):
            person = players.setdefault(row['id'], dict(row, yellow_cards=0, red_cards=0))
            person['yellow_cards'] += row['yellows']
            person['red_cards'] += row['reds'] + int(row['yellows'] >= 2)
            person['is_suspended'] = state['player',row['id']]['blocked']
        return sorted(players.values(), key=lambda p:(-p['red_cards'],-p['yellow_cards'],p['last_name']))[:limit]

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
        from discipline import disciplinary_state
        state = disciplinary_state(conn)
        players = [dict(p, is_suspended=state['player',p['id']]['blocked']) for p in players]
        staff = [dict(p, is_suspended=state['staff',p['id']]['blocked']) for p in staff]
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
            SELECT SUM(ml.minutes_played) as total_min, SUM(CASE WHEN ml.is_starter = 1 OR EXISTS (SELECT 1 FROM match_substitutions ms WHERE ms.match_id = ml.match_id AND ms.player_in_id = ml.player_id) THEN 1 ELSE 0 END) as apps
            FROM match_lineups ml
            JOIN matches m ON ml.match_id = m.id
            WHERE ml.player_id = ? AND m.status = 'VERIFIED'
        """, (player_id,)).fetchone()

        if minutes_row:
            stats["minutes"] = minutes_row["total_min"] or 0
            stats["appearances"] = minutes_row["apps"] or 0

        stats['red_cards'] += conn.execute("""SELECT COUNT(*) FROM (
            SELECT e.match_id FROM match_events e JOIN matches m ON m.id=e.match_id
            WHERE m.status='VERIFIED' AND e.player_id=? AND e.event_type='YELLOW_CARD'
            GROUP BY e.match_id HAVING COUNT(*)>=2)""", (player_id,)).fetchone()[0]
        from discipline import disciplinary_state
        player = dict(player, is_suspended=disciplinary_state(conn)['player',player_id]['blocked'])
        return render_template("player_detail.html", player=player, stats=stats)

@app.route('/admin')
@roles_required('team_admin', 'referee', 'organizer')
def admin_panel():
    from discipline import disciplinary_state
    with db_connection() as conn:
        teams = conn.execute('SELECT id,name FROM teams ORDER BY name').fetchall()
        matches = conn.execute('''SELECT m.*, h.name AS home_name, a.name AS away_name
            FROM matches m JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
            ORDER BY m.gameweek,m.id''').fetchall()
        if g.user['role'] == 'team_admin':
            matches = [m for m in matches if g.user['team_id'] in (m['home_team_id'],m['away_team_id'])]
        elif g.user['role'] == 'referee':
            matches = [m for m in matches if m['referee_user_id'] == g.user['id']]
        referees = conn.execute("SELECT id,username FROM users WHERE role='referee' ORDER BY username").fetchall()
        state = disciplinary_state(conn)
        if g.user['role'] == 'team_admin':
            state = {key:value for key,value in state.items() if value['person']['team_id'] == g.user['team_id']}
        return render_template('admin.html', teams=teams, matches=matches, referees=referees, discipline=state)


def match_date_value():
    from datetime import datetime
    value = request.form.get('match_date', '').strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        abort(400, 'Укажите дату и время матча')
    if parsed.tzinfo is not None:
        abort(400, 'Укажите местное время без часового пояса')
    return parsed.isoformat(timespec='minutes')


def referee_id_value(conn):
    referee_id = form_int('referee_user_id')
    if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='referee'", (referee_id,)).fetchone():
        abort(400, 'Выберите учётную запись судьи')
    return referee_id


@app.post('/admin/create-fixture')
@roles_required('organizer')
def create_fixture():
    home_id, away_id = form_int('home_team_id'), form_int('away_team_id')
    gameweek = form_int('gameweek', 1, 38)
    date = match_date_value()
    with db_connection(write=True) as conn:
        if home_id == away_id or conn.execute('SELECT COUNT(*) FROM teams WHERE id IN (?,?)', (home_id,away_id)).fetchone()[0] != 2:
            abort(400, 'Выберите две разные команды')
        referee = referee_id_value(conn)
        match_id = conn.execute("INSERT INTO matches (gameweek,home_team_id,away_team_id,status,is_finished,referee_user_id,match_date) VALUES (?,?,?,'SCHEDULED',0,?,?)", (gameweek,home_id,away_id,referee,date)).lastrowid
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/assign-referee')
@roles_required('organizer')
def assign_referee(match_id):
    with db_connection(write=True) as conn:
        match_row(conn,match_id,editable=True)
        if has_match_events(conn,match_id):
            abort(409,'Сначала удалите события, чтобы изменить назначение и дату')
        referee = referee_id_value(conn)
        date = match_date_value()
        conn.execute('UPDATE matches SET referee_user_id=?,match_date=? WHERE id=?', (referee,date,match_id))
        conn.execute("UPDATE match_team_submissions SET status='SUBMITTED',checked_by=NULL WHERE match_id=? AND status='APPROVED'", (match_id,))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.route('/matches/<int:match_id>/protocol')
def match_protocol(match_id):
    from discipline import disciplinary_state
    with db_connection() as conn:
        match = conn.execute('''SELECT m.*, h.name AS home_name,a.name AS away_name FROM matches m
            JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id WHERE m.id=?''',(match_id,)).fetchone()
        if not match:
            abort(404)
        if match['status'] != 'VERIFIED':
            if not g.user:
                return redirect(url_for('login'))
            if g.user['role'] == 'team_admin' and g.user['team_id'] not in (match['home_team_id'],match['away_team_id']):
                abort(403)
            if g.user['role'] == 'referee' and match['referee_user_id'] != g.user['id']:
                abort(403)
        state = disciplinary_state(conn,before_match=match)
        panels = []
        for team_id,name in [(match['home_team_id'],match['home_name']),(match['away_team_id'],match['away_name'])]:
            players = conn.execute('''SELECT p.*,ml.id AS lineup_id,ml.is_starter,ml.minutes_played,ml.is_captain,COALESCE(ml.is_goalkeeper,p.position='GK') AS is_goalkeeper
                FROM players p LEFT JOIN match_lineups ml ON ml.player_id=p.id AND ml.match_id=?
                WHERE p.team_id=? ORDER BY p.jersey_number,p.id''',(match_id,team_id)).fetchall()
            staff = conn.execute('''SELECT s.*,ms.staff_id AS selected,ms.role AS match_role FROM staff s
                LEFT JOIN match_staff ms ON ms.staff_id=s.id AND ms.match_id=? WHERE s.team_id=? ORDER BY s.id''',(match_id,team_id)).fetchall()
            submission=conn.execute('SELECT * FROM match_team_submissions WHERE match_id=? AND team_id=?',(match_id,team_id)).fetchone()
            players=[dict(p,is_foreign=is_foreign(p['nationality']),blocked=state['player',p['id']]['blocked']) for p in players]
            staff=sorted([dict(s,is_head_coach=canonical_role(s['match_role'] or s['role'])=='head_coach') for s in staff],key=lambda s:(canonical_role(s['match_role'] or s['role'])!='head_coach',s['id']))
            starters=[p for p in players if p['lineup_id'] and p['is_starter']]
            bench=[p for p in players if p['lineup_id'] and not p['is_starter']]
            panels.append(dict(id=team_id,name=name,players=players,staff=staff,
                starters=starters,bench=bench,status=submission['status'] if submission else 'DRAFT'))
        events = conn.execute('''SELECT e.*,p.first_name,p.last_name FROM match_events e JOIN players p ON p.id=e.player_id
            WHERE match_id=? ORDER BY minute,e.id''',(match_id,)).fetchall()
        staff_events = conn.execute('''SELECT e.*,s.first_name,s.last_name FROM staff_events e JOIN staff s ON s.id=e.staff_id
            WHERE match_id=? ORDER BY minute,e.id''',(match_id,)).fetchall()
        substitutions = conn.execute('''SELECT ms.*,po.last_name AS out_name,pi.last_name AS in_name FROM match_substitutions ms
            JOIN players po ON po.id=ms.player_out_id JOIN players pi ON pi.id=ms.player_in_id WHERE match_id=? ORDER BY minute,ms.id''',(match_id,)).fetchall()
        starters=[p['id'] for panel in panels for p in panel['starters']]
        field_positions=event_field_positions(starters,substitutions,events)
        events=[dict(e,off_field=not field_positions[e['id']]) for e in events]
        event_context=dict(starters=starters,substitutions=[dict(s) for s in substitutions],events=events)
        referees=conn.execute("SELECT id,username FROM users WHERE role='referee'").fetchall()
        is_referee=bool(g.user and g.user['role']=='referee' and match['referee_user_id']==g.user['id'])
        editable=match['status'] in ('SCHEDULED','DRAFT')
        is_organizer=bool(g.user and g.user['role']=='organizer')
        ready=lineups_ready(conn,match_id) and all(match[field] for field in ('referee_name','assistant_one','assistant_two','fourth_official'))
        event_editable=editable and ready and (is_organizer or (is_referee and all(p['status']=='APPROVED' for p in panels)))
        from confirmations import confirmation_status, protocol_hash
        confirmations=confirmation_status(conn,match)
        content_hash=protocol_hash(conn,match_id)
        officials=conn.execute('SELECT name FROM officials ORDER BY name').fetchall()
        return render_template('protocol.html',match=match,panels=panels,discipline=state,events=events,staff_events=staff_events,
                               substitutions=substitutions,referees=referees,is_referee=is_referee,is_organizer=is_organizer,confirmations=confirmations,content_hash=content_hash,officials=officials,event_context=event_context,editable=editable,event_editable=event_editable)


def team_match(conn,match_id):
    match=match_row(conn,match_id,editable=True)
    organizer=g.user['role']=='organizer'
    team=form_int('team_id') if organizer else g.user['team_id']
    if team not in (match['home_team_id'],match['away_team_id']):
        abort(403,'Это не матч вашей команды')
    submission=conn.execute('SELECT status FROM match_team_submissions WHERE match_id=? AND team_id=?',(match_id,team)).fetchone()
    if not organizer and submission and submission['status'] != 'DRAFT':
        abort(409,'Заявка уже отправлена: судья должен вернуть её на доработку')
    if not organizer and has_match_events(conn,match_id):
        abort(409,'Матч уже имеет события; составы зафиксированы')
    return match,team


def has_match_events(conn,match_id):
    return any(conn.execute(f'SELECT 1 FROM {table} WHERE match_id=?',(match_id,)).fetchone()
               for table in ('match_events','match_substitutions','staff_events'))


def selected_ids(name):
    try:
        values=[int(x) for x in request.form.getlist(name) if x.strip()]
    except ValueError:
        abort(400,'Некорректный список участников')
    if len(values) != len(set(values)):
        abort(400,'Участник выбран дважды')
    return values


@app.post('/matches/<int:match_id>/lineups')
@roles_required('team_admin', 'organizer')
def save_lineups(match_id):
    starters,bench,staff=selected_ids('starters'),selected_ids('bench'),selected_ids('staff')
    if set(starters)&set(bench):
        abort(400,'Игрок не может быть одновременно в старте и запасе')
    with db_connection(write=True) as conn:
        match,team=team_match(conn,match_id)
        player_rows={r['id']:r for r in conn.execute('SELECT id,position FROM players WHERE team_id=?',(team,))}
        player_ids=set(player_rows)
        keepers,captains=selected_ids('goalkeepers'),selected_ids('captains')
        if not set(keepers+captains)<=set(starters+bench) or len(captains)>1:
            abort(400,'Пометки должны относиться к выбранным игрокам; капитан только один')
        staff_rows={r['id']:r for r in conn.execute('SELECT * FROM staff WHERE team_id=?',(team,))}
        if not set(starters+bench)<=player_ids or not set(staff)<=staff_rows.keys():
            abort(403,'В заявке могут быть только участники своей команды')
        conn.execute('DELETE FROM match_lineups WHERE match_id=? AND team_id=?',(match_id,team))
        conn.execute('DELETE FROM match_staff WHERE match_id=? AND team_id=?',(match_id,team))
        for player in starters+bench:
            conn.execute('INSERT INTO match_lineups (match_id,player_id,team_id,is_starter,is_goalkeeper,is_captain,minute_in,minute_out,minutes_played) VALUES (?,?,?,?,?,?,0,90,0)',(match_id,player,team,int(player in starters),int(player in keepers or player_rows[player]['position']=='GK'),int(player in captains)))
        for member in staff:
            conn.execute('INSERT INTO match_staff (match_id,staff_id,team_id,role) VALUES (?,?,?,?)',(match_id,member,team,staff_rows[member]['role']))
        validate_team_lineup(conn,match_id,team)
        calculate_minutes(conn,match_id)
        validate_staff_events(conn,match_id)
        conn.execute("INSERT INTO match_team_submissions (match_id,team_id,status) VALUES (?,?,'DRAFT') ON CONFLICT(match_id,team_id) DO UPDATE SET status='DRAFT',checked_by=NULL",(match_id,team))
        conn.execute("UPDATE matches SET status='DRAFT' WHERE id=?",(match_id,))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/submit-lineup')
@roles_required('team_admin', 'organizer')
def submit_lineup(match_id):
    with db_connection(write=True) as conn:
        match,team=team_match(conn,match_id)
        validate_team_lineup(conn,match_id,team)
        conn.execute("UPDATE match_team_submissions SET status='SUBMITTED' WHERE match_id=? AND team_id=?",(match_id,team))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/check-lineup/<int:team_id>')
@roles_required('referee', 'organizer')
def check_lineup(match_id,team_id):
    with db_connection(write=True) as conn:
        match=require_referee(conn,match_id,approved=False)
        if team_id not in (match['home_team_id'],match['away_team_id']):
            abort(400)
        row=conn.execute('SELECT status FROM match_team_submissions WHERE match_id=? AND team_id=?',(match_id,team_id)).fetchone()
        if not row or row['status'] != 'SUBMITTED':
            abort(409,'Команда должна сначала отправить заявку')
        validate_team_lineup(conn,match_id,team_id)
        conn.execute("UPDATE match_team_submissions SET status='APPROVED',checked_by=? WHERE match_id=? AND team_id=?",(g.user['username'],match_id,team_id))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/return-lineup/<int:team_id>')
@roles_required('referee', 'organizer')
def return_lineup(match_id,team_id):
    with db_connection(write=True) as conn:
        match=require_referee(conn,match_id,approved=False)
        if team_id not in (match['home_team_id'],match['away_team_id']):
            abort(400)
        if has_match_events(conn,match_id):
            abort(409,'Сначала удалите события и замены матча')
        conn.execute("UPDATE match_team_submissions SET status='DRAFT',checked_by=NULL WHERE match_id=? AND team_id=?",(match_id,team_id))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/teams/<int:team_id>/staff')
@roles_required('team_admin', 'organizer')
def add_staff(team_id):
    if g.user['role'] != 'organizer' and team_id != g.user['team_id']:
        abort(403)
    fields={name:request.form.get(name,'').strip() for name in ('first_name','last_name','role','nationality')}
    if any(not value or len(value)>100 for value in fields.values()):
        abort(400,'Заполните имя, фамилию, роль и гражданство (до 100 символов)')
    with db_connection(write=True) as conn:
        conn.execute('INSERT INTO staff (team_id,first_name,last_name,role,nationality) VALUES (?,?,?,?,?)',(team_id,fields['first_name'],fields['last_name'],fields['role'],fields['nationality']))
    return redirect(url_for('team_detail',team_id=team_id))


@app.post('/matches/<int:match_id>/officials')
@roles_required('referee', 'organizer')
def save_officials(match_id):
    required=('referee_name','assistant_one','assistant_two','fourth_official')
    optional=('var_official','avar_official')
    fields={name:request.form.get(name,'').strip() for name in required+optional}
    if any(not fields[name] for name in required) or any(len(value)>150 for value in fields.values()):
        abort(400,'Заполните четырёх обязательных судей')
    with db_connection(write=True) as conn:
        require_referee(conn,match_id,approved=False)
        known={row['name'] for row in conn.execute('SELECT name FROM officials')}
        if any(value and value not in known for value in fields.values()):
            abort(400,'Выберите судей из справочника')
        conn.execute('UPDATE matches SET referee_name=?,assistant_one=?,assistant_two=?,fourth_official=?,var_official=?,avar_official=? WHERE id=?',(*fields.values(),match_id))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/add-event')
@roles_required('referee', 'organizer')
def add_match_event(match_id):
    player_id,minute=form_int('player_id'),form_int('minute',1,90)
    kind=request.form.get('event_type')
    if kind not in ('GOAL','PENALTY','OWN_GOAL','YELLOW_CARD','RED_CARD'):
        abort(400,'Неизвестное событие')
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        validate_lineups(conn,match_id)
        player=conn.execute('SELECT team_id FROM match_lineups WHERE match_id=? AND player_id=?',(match_id,player_id)).fetchone()
        if not player:
            abort(400,'Игрок отсутствует в заявке')
        conn.execute('INSERT INTO match_events (match_id,team_id,player_id,event_type,minute) VALUES (?,?,?,?,?)',(match_id,player['team_id'],player_id,kind,minute))
        calculate_minutes(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/staff-event')
@roles_required('referee', 'organizer')
def add_staff_event(match_id):
    member,minute=form_int('staff_id'),form_int('minute',1,90)
    kind=request.form.get('event_type')
    if kind not in ('YELLOW_CARD','RED_CARD'):
        abort(400)
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        validate_lineups(conn,match_id)
        staff=conn.execute('SELECT team_id FROM match_staff WHERE match_id=? AND staff_id=?',(match_id,member)).fetchone()
        if not staff:
            abort(400,'Член штаба отсутствует в заявке')
        conn.execute('INSERT INTO staff_events (match_id,team_id,staff_id,event_type,minute) VALUES (?,?,?,?,?)',(match_id,staff['team_id'],member,kind,minute))
        validate_staff_events(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/delete-event/<int:event_id>')
@roles_required('referee', 'organizer')
def delete_match_event(match_id,event_id):
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        conn.execute('DELETE FROM match_events WHERE id=? AND match_id=?',(event_id,match_id))
        calculate_minutes(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/delete-staff-event/<int:event_id>')
@roles_required('referee', 'organizer')
def delete_staff_event(match_id,event_id):
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        conn.execute('DELETE FROM staff_events WHERE id=? AND match_id=?',(event_id,match_id))
        validate_staff_events(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/make-substitution')
@roles_required('referee', 'organizer')
def make_substitution(match_id):
    outgoing,incoming,minute=form_int('player_out_id'),form_int('player_in_id'),form_int('minute',1,90)
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        validate_lineups(conn,match_id)
        if outgoing == incoming or conn.execute('SELECT 1 FROM match_substitutions WHERE match_id=? AND (player_out_id=? OR player_in_id=?)',(match_id,outgoing,incoming)).fetchone():
            abort(400,'Некорректная или повторная замена')
        conn.execute('INSERT INTO match_substitutions (match_id,player_out_id,player_in_id,minute) VALUES (?,?,?,?)',(match_id,outgoing,incoming,minute))
        calculate_minutes(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/delete-substitution/<int:substitution_id>')
@roles_required('referee', 'organizer')
def delete_substitution(match_id,substitution_id):
    with db_connection(write=True) as conn:
        require_referee(conn,match_id)
        conn.execute('DELETE FROM match_substitutions WHERE id=? AND match_id=?',(substitution_id,match_id))
        calculate_minutes(conn,match_id)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/submit-for-review')
@roles_required('referee', 'organizer')
def submit_for_review(match_id):
    with db_connection(write=True) as conn:
        match=require_referee(conn,match_id)
        if not match['match_date']:
            abort(400,'Организатор должен указать дату и время матча')
        validate_lineups(conn,match_id)
        calculate_minutes(conn,match_id)
        validate_staff_events(conn,match_id)
        conn.execute("UPDATE matches SET status='PENDING_REVIEW' WHERE id=?",(match_id,))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/verify-protocol')
@roles_required('organizer')
def verify_protocol(match_id):
    from discipline import roster_conflicts, assert_no_new_roster_conflicts
    with db_connection(write=True) as conn:
        previous_conflicts=roster_conflicts(conn)
        match=match_row(conn,match_id)
        if match['status'] != 'PENDING_REVIEW':
            abort(409,'Судья должен отправить протокол на проверку')
        if not match['match_date'] or not match['referee_user_id'] or not all(match[field] for field in ('referee_name','assistant_one','assistant_two','fourth_official')):
            abort(400,'Не заполнены назначение, дата или судейская бригада')
        # Participant confirmations are separate from organizer approval.
        validate_lineups(conn,match_id)
        calculate_minutes(conn,match_id)
        validate_staff_events(conn,match_id)
        home=away=0
        for event in conn.execute('SELECT * FROM match_events WHERE match_id=?',(match_id,)):
            if event['event_type'] in ('GOAL','PENALTY','OWN_GOAL'):
                is_home=event['team_id']==match['home_team_id']
                if event['event_type']=='OWN_GOAL':
                    is_home=not is_home
                if is_home:
                    home+=1
                else:
                    away+=1
        conn.execute("UPDATE matches SET home_score=?,away_score=?,status='VERIFIED',is_finished=1,verified_by=? WHERE id=?",(home,away,g.user['username'],match_id))
        assert_no_new_roster_conflicts(conn,previous_conflicts)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/reopen-protocol')
@roles_required('organizer')
def reopen_protocol(match_id):
    from discipline import roster_conflicts, assert_no_new_roster_conflicts
    with db_connection(write=True) as conn:
        previous_conflicts=roster_conflicts(conn)
        match=match_row(conn,match_id)
        if match['status'] not in ('VERIFIED','PENDING_REVIEW'):
            abort(409,'Протокол не находится на проверке')
        conn.execute("UPDATE matches SET status='DRAFT',is_finished=0,verified_by=NULL WHERE id=?",(match_id,))
        assert_no_new_roster_conflicts(conn,previous_conflicts)
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/matches/<int:match_id>/confirm')
@roles_required('team_admin', 'referee')
def confirm_protocol(match_id):
    from confirmations import protocol_hash
    with db_connection(write=True) as conn:
        match=match_row(conn,match_id)
        if match['status'] not in ('PENDING_REVIEW','VERIFIED'):
            abort(409,'Подтверждение доступно для готового итогового протокола')
        if g.user['role']=='team_admin':
            if g.user['team_id'] not in (match['home_team_id'],match['away_team_id']):
                abort(403)
            scope=f"team:{g.user['team_id']}"
        else:
            if match['referee_user_id']!=g.user['id']:
                abort(403)
            scope='referee'
        digest=protocol_hash(conn,match_id)
        if request.form.get('content_hash')!=digest:
            abort(409,'Протокол изменился. Обновите страницу и проверьте его заново')
        conn.execute('''INSERT INTO protocol_confirmations (match_id,scope,confirmed_by,content_hash)
            VALUES (?,?,?,?) ON CONFLICT(match_id,scope) DO UPDATE SET confirmed_by=excluded.confirmed_by,
            content_hash=excluded.content_hash,confirmed_at=CURRENT_TIMESTAMP''',
            (match_id,scope,g.user['id'],digest))
    return redirect(url_for('match_protocol',match_id=match_id))


@app.post('/discipline/decision')
@roles_required('organizer')
def disciplinary_decision():
    from discipline import disciplinary_state, order_key
    match_id,subject,total=form_int('match_id'),form_int('subject_id'),form_int('total_games',1,1000)
    kind,reason=request.form.get('subject_type'),request.form.get('reason')
    explanation=request.form.get('explanation','').strip()
    if not explanation or len(explanation)>2000:
        abort(400,'Укажите решение КДК (до 2000 символов)')
    with db_connection(write=True) as conn:
        state=disciplinary_state(conn).get((kind,subject))
        ban = next((b for b in state['bans'] if b['match_id']==match_id and b['reason']==reason),None) if state else None
        if not ban:
            abort(400,'Санкция не найдена в утверждённых протоколах')
        cutoff = max(conn.execute("SELECT * FROM matches WHERE status='VERIFIED' AND (home_team_id=? OR away_team_id=?)", (state['person']['team_id'],state['person']['team_id'])),key=order_key)
        served = ban['total_games']-ban['remaining']
        conn.execute('''INSERT INTO disciplinary_decision_history
            (match_id,subject_type,subject_id,reason,total_games,served_games,effective_after_match_id,explanation,decided_by)
            VALUES (?,?,?,?,?,?,?,?,?)''', (match_id,kind,subject,reason,total,served,cutoff['id'],explanation,g.user['username']))
        conn.execute('''INSERT INTO disciplinary_decisions (match_id,subject_type,subject_id,reason,total_games,explanation,decided_by)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(match_id,subject_type,subject_id,reason) DO UPDATE SET
            total_games=excluded.total_games,explanation=excluded.explanation,decided_by=excluded.decided_by''',
            (match_id,kind,subject,reason,total,explanation,g.user['username']))
    return redirect(url_for('admin_panel'))


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
def request_error(error):
    return render_template('error.html',error=error),error.code


if __name__ == '__main__':
    app.run(debug=False,port=5001)
