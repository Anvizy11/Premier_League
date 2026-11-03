"""Idempotent migration preserving existing accounts and competition records."""

from premier_league.paths import SCHEMA_PATH


def initialize_database(conn):
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    users = conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()
    if users and "team_admin" not in users[0]:
        # The previous global administrator/reviewer accounts become organizers.
        conn.execute(
            """CREATE TABLE users_new (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('team_admin','referee','organizer')),
            team_id INTEGER REFERENCES teams(id),
            CHECK ((role='team_admin' AND team_id IS NOT NULL) OR (role!='team_admin' AND team_id IS NULL)))"""
        )
        conn.execute(
            "INSERT INTO users_new (id,username,password_hash,role) SELECT id,username,password_hash,'organizer' FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
    match_columns = {row[1] for row in conn.execute("PRAGMA table_info(matches)")}
    if match_columns:
        for name, kind in [
            ("referee_user_id", "INTEGER REFERENCES users(id)"),
            ("assistant_one", "TEXT"),
            ("assistant_two", "TEXT"),
            ("fourth_official", "TEXT"),
            ("match_date", "TEXT"),
            ("var_official", "TEXT"),
            ("avar_official", "TEXT"),
        ]:
            if name not in match_columns:
                conn.execute(f"ALTER TABLE matches ADD COLUMN {name} {kind}")
    # Execute statements separately to keep migration within the caller's transaction.
    for statement in SCHEMA_PATH.read_text().split(";"):
        if statement.strip():
            conn.execute(statement)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(match_lineups)")}
    for name, kind in [
        ("is_captain", "INTEGER NOT NULL DEFAULT 0 CHECK(is_captain IN (0,1))"),
        ("is_goalkeeper", "INTEGER CHECK(is_goalkeeper IN (0,1))"),
    ]:
        if name not in columns:
            conn.execute(f"ALTER TABLE match_lineups ADD COLUMN {name} {kind}")
    from premier_league.services.officials import seed_officials

    seed_officials(conn)
