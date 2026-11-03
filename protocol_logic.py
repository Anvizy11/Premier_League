"""Validation and deterministic calculation for a 90-minute match."""
from flask import abort, request


def form_int(name, minimum=1, maximum=None):
    try:
        value = int(request.form[name])
    except (ValueError, KeyError):
        abort(400, 'Некорректное числовое поле')
    if value < minimum or (maximum is not None and value > maximum):
        abort(400, 'Число вне допустимого диапазона')
    return value


def match_row(conn, match_id, editable=False):
    match = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
    if not match:
        abort(404)
    if editable and match['status'] not in ('SCHEDULED', 'DRAFT'):
        abort(409, 'Сначала верните протокол на доработку')
    return match


def canonical_role(value):
    value = ' '.join(value.strip().casefold().split())
    return {'head coach': 'head_coach', 'главный тренер': 'head_coach',
            'doctor': 'doctor', 'врач': 'doctor'}.get(value, value)


def validate_team_lineup(conn, match_id, team_id):
    from discipline import check_eligible
    match = match_row(conn, match_id)
    rows = conn.execute("SELECT ml.*, COALESCE(ml.is_goalkeeper,p.position='GK') AS goalkeeper, p.position, p.team_id AS actual_team FROM match_lineups ml JOIN players p ON p.id=ml.player_id WHERE ml.match_id=? AND ml.team_id=?", (match_id, team_id)).fetchall()
    starters = [p for p in rows if p['is_starter']]
    if not 7 <= len(starters) <= 11 or len(rows) - len(starters) > 12:
        abort(400, 'Нужно 7–11 игроков в старте и не более 12 запасных')
    if sum(p['goalkeeper'] for p in starters) != 1:
        abort(400, 'В стартовом составе должен быть один вратарь')
    if sum(p['is_captain'] for p in rows) > 1:
        abort(400,'В заявке может быть только один капитан')
    if any(p['actual_team'] != team_id for p in rows):
        abort(400, 'Игрок другой команды')
    staff = conn.execute('SELECT ms.*, s.team_id AS actual_team FROM match_staff ms JOIN staff s ON s.id=ms.staff_id WHERE ms.match_id=? AND ms.team_id=?', (match_id, team_id)).fetchall()
    if not 2 <= len(staff) <= 10 or any(p['actual_team'] != team_id for p in staff):
        abort(400, 'Нужно от 2 до 10 членов штаба своей команды')
    if not {'head_coach', 'doctor'} <= {canonical_role(p['role']) for p in staff}:
        abort(400, 'В штабе обязательны главный тренер и врач')
    check_eligible(conn, match, 'player', [p['player_id'] for p in rows])
    check_eligible(conn, match, 'staff', [p['staff_id'] for p in staff])


def validate_lineups(conn, match_id):
    match = match_row(conn, match_id)
    for team in (match['home_team_id'], match['away_team_id']):
        validate_team_lineup(conn, match_id, team)


def require_referee(conn, match_id, editable=True, approved=True):
    from flask import g
    match = match_row(conn, match_id, editable=editable)
    organizer = g.user['role'] == 'organizer'
    if not organizer and match['referee_user_id'] != g.user['id']:
        abort(403, 'Доступ есть только у назначенного судьи матча')
    if approved:
        count = conn.execute("SELECT COUNT(*) FROM match_team_submissions WHERE match_id=? AND status='APPROVED' AND team_id IN (?,?)", (match_id, match['home_team_id'], match['away_team_id'])).fetchone()[0]
        if not organizer and count != 2:
            abort(409, 'Сначала проверьте и подтвердите заявки обеих команд')
        if not all(match[key] and match[key].strip() for key in ('referee_name','assistant_one','assistant_two','fourth_official')):
            abort(400, 'Заполните судейскую бригаду')
    return match


def calculate_minutes(conn, match_id):
    rows = conn.execute('SELECT * FROM match_lineups WHERE match_id=?', (match_id,)).fetchall()
    intervals = {p['player_id']: [0 if p['is_starter'] else None, 90] for p in rows}
    teams = {p['player_id']: p['team_id'] for p in rows}
    active = {p["player_id"] for p in rows if p["is_starter"]}
    yellow_counts = {}
    dismissed = set()
    roster_ids = set(intervals)
    timeline = []
    for sub in conn.execute('SELECT * FROM match_substitutions WHERE match_id=?', (match_id,)):
        timeline.append((sub['minute'], 0, sub['id'], 'sub', sub['player_out_id'], sub['player_in_id']))
    for event in conn.execute('SELECT * FROM match_events WHERE match_id=?', (match_id,)):
        timeline.append((event['minute'], 1, event['id'], event['event_type'], event['player_id'], None))
    for minute, _, _, kind, player, incoming in sorted(timeline):
        interval = intervals.get(player)
        if player not in roster_ids or player in dismissed:
            abort(400, 'Событие относится к отсутствующему или удалённому игроку')
        if kind not in ('YELLOW_CARD', 'RED_CARD') and player not in active:
            abort(400, 'Игрок не находился на поле')
        if kind == 'sub':
            target = intervals.get(incoming)
            if incoming in dismissed or not target or teams[player] != teams[incoming] or target[0] is not None or interval[1] != 90:
                abort(400, 'Некорректная замена')
            interval[1] = minute
            target[0] = minute
            active.remove(player)
            active.add(incoming)
        elif kind in ('RED_CARD', 'YELLOW_CARD'):
            if kind == 'YELLOW_CARD':
                yellow_counts[player] = yellow_counts.get(player, 0) + 1
            if kind == 'RED_CARD' or yellow_counts.get(player, 0) == 2:
                dismissed.add(player)
                if player in active:
                    interval[1] = minute
                    active.remove(player)
    for player, (start, end) in intervals.items():
        conn.execute('UPDATE match_lineups SET minute_in=?, minute_out=?, minutes_played=? WHERE match_id=? AND player_id=?',
                     (start if start is not None else 0, end, max(0, end-start) if start is not None else 0, match_id, player))


def validate_staff_events(conn, match_id):
    roster = {r['staff_id'] for r in conn.execute('SELECT staff_id FROM match_staff WHERE match_id=?', (match_id,))}
    yellows, dismissed = {}, set()
    for event in conn.execute('SELECT * FROM staff_events WHERE match_id=? ORDER BY minute,id', (match_id,)):
        who = event['staff_id']
        if who not in roster or who in dismissed:
            abort(400, 'Член штаба отсутствует в заявке или уже удалён')
        if event['event_type'] == 'YELLOW_CARD':
            yellows[who] = yellows.get(who, 0) + 1
        if event['event_type'] == 'RED_CARD' or yellows.get(who, 0) == 2:
            dismissed.add(who)


def lineups_ready(conn, match_id):
    """Use the same validation for UI gating and write endpoints."""
    from werkzeug.exceptions import HTTPException
    try:
        validate_lineups(conn, match_id)
    except HTTPException:
        return False
    return True


def is_foreign(nationality):
    return nationality.strip().casefold() not in ('англия', 'england')


def event_field_positions(starters, substitutions, events):
    """Field presence immediately before each event; same ordering as minute validation."""
    active=set(starters)
    yellows={}
    positions={}
    timeline=[(s['minute'],0,s['id'],'sub',s) for s in substitutions]
    timeline += [(e['minute'],1,e['id'],'event',e) for e in events]
    for _,_,_,kind,item in sorted(timeline,key=lambda entry:entry[:3]):
        if kind=='sub':
            active.discard(item['player_out_id'])
            active.add(item['player_in_id'])
        else:
            player=item['player_id']
            positions[item['id']]=player in active
            if item['event_type']=='YELLOW_CARD':
                yellows[player]=yellows.get(player,0)+1
            if item['event_type']=='RED_CARD' or yellows.get(player,0)>=2:
                active.discard(player)
    return positions
