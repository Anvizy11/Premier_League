"""Identity validation and age calculation for players and staff."""

from datetime import date, datetime
import unicodedata
from zoneinfo import ZoneInfo

from flask import abort


def competition_today():
    return datetime.now(ZoneInfo("Europe/Istanbul")).date()


def normalize_name(value):
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def person_fields(form):
    fields = {
        name: " ".join(form.get(name, "").split())
        for name in ("first_name", "last_name", "nationality")
    }
    if any(not value or len(value) > 100 for value in fields.values()):
        abort(400, "Заполните имя, фамилию и гражданство (до 100 символов)")
    birth_text = form.get("birth_date", "").strip()
    try:
        birth = date.fromisoformat(birth_text)
    except ValueError:
        abort(400, "Укажите корректную дату рождения")
    if birth.isoformat() != birth_text or birth > competition_today():
        abort(400, "Дата рождения должна быть корректной и не позже сегодняшней даты")
    fields["birth_date"] = birth.isoformat()
    return fields


def calculate_age(birth_date, today=None):
    if not birth_date:
        return None
    try:
        birth = date.fromisoformat(birth_date)
    except ValueError:
        return None
    today = today or competition_today()
    if birth > today:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def check_person_unique(conn, table, fields):
    if table not in ("players", "staff"):
        raise ValueError("Unsupported person table")
    candidates = conn.execute(
        f"SELECT first_name,last_name FROM {table} WHERE birth_date=?",
        (fields["birth_date"],),
    ).fetchall()
    identity = (normalize_name(fields["first_name"]), normalize_name(fields["last_name"]))
    for person in candidates:
        existing = (normalize_name(person["first_name"]), normalize_name(person["last_name"]))
        if existing == identity:
            abort(409, "Участник с такими именем, фамилией и датой рождения уже есть в базе")
