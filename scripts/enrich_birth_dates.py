"""Import reviewed birth dates. Preview by default; --apply creates a backup."""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from premier_league.database import DATABASE_NAME, db_connection
from premier_league.services.people import competition_today
import os

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "birth_dates.json"


def plan_updates(conn, records, include_synthetic=False):
    updates = []
    seen = set()
    for record in records:
        table = {"player": "players", "staff": "staff"}[record["kind"]]
        if record["synthetic"] and not include_synthetic:
            continue
        birth = date.fromisoformat(record["birth_date"])
        if birth.isoformat() != record["birth_date"] or birth > competition_today():
            raise ValueError("Invalid birth date")
        if not record["synthetic"] and not record["source_url"].startswith("https://"):
            raise ValueError("Real dates require a source URL")
        rows = conn.execute(
            f"""SELECT p.id,p.birth_date FROM {table} p JOIN teams t ON t.id=p.team_id
            WHERE p.first_name=? AND p.last_name=? AND t.name=?""",
            (record["first_name"], record["last_name"], record["team"]),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError(
                f"Expected one participant: {record['first_name']} {record['last_name']}"
            )
        row = rows[0]
        key = (table, row["id"])
        if key in seen:
            raise ValueError("Duplicate participant in import file")
        seen.add(key)
        if row["birth_date"]:
            if row["birth_date"] != record["birth_date"]:
                raise ValueError(
                    f"Existing date differs for {record['first_name']} {record['last_name']}"
                )
            continue
        updates.append((table, row["id"], record["birth_date"]))
    return updates


def apply_updates(conn, updates):
    for table, person_id, birth_date in updates:
        if table not in ("players", "staff"):
            raise ValueError("Invalid participant table")
        conn.execute(
            f"UPDATE {table} SET birth_date=? WHERE id=? AND (birth_date IS NULL OR birth_date='')",
            (birth_date, person_id),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--include-synthetic",
        action="store_true",
        help="Include authorized test dates for generated doctors",
    )
    args = parser.parse_args()
    records = json.loads(DATA_PATH.read_text())["records"]
    backup = None
    with db_connection(write=args.apply) as conn:
        updates = plan_updates(conn, records, args.include_synthetic)
        if args.apply and updates:
            database = Path(os.environ.get("PREMIER_LEAGUE_DATABASE", DATABASE_NAME)).resolve()
            folder = database.parent / "backups"
            folder.mkdir(exist_ok=True)
            backup = (
                folder / f"{database.stem}_before_birth_dates_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
            )
            with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as source:
                with sqlite3.connect(backup) as target:
                    source.backup(target)
            apply_updates(conn, updates)
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
    print(f"{'Updated' if args.apply else 'Would update'}: {len(updates)}")
    if backup:
        print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
