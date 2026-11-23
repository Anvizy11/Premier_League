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
    staff_columns = {row[1] for row in conn.execute("PRAGMA table_info(staff)")}
    if staff_columns and "birth_date" not in staff_columns:
        conn.execute("ALTER TABLE staff ADD COLUMN birth_date TEXT")
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
    initialize_event_order(conn)


def initialize_event_order(conn):
    """Record a common insertion order across the three event tables."""
    sources = (
        ("match_events", "player"),
        ("staff_events", "staff"),
        ("match_substitutions", "substitution"),
    )
    for table, kind in sources:
        # Triggers run in the source write transaction, including its rollback.
        conn.execute(
            f"""CREATE TRIGGER IF NOT EXISTS {table}_timeline_insert
            AFTER INSERT ON {table}
            BEGIN
                INSERT INTO match_timeline_order (match_id,event_kind,event_id)
                VALUES (NEW.match_id,'{kind}',NEW.id);
            END"""
        )
        conn.execute(
            f"""CREATE TRIGGER IF NOT EXISTS {table}_timeline_delete
            AFTER DELETE ON {table}
            BEGIN
                DELETE FROM match_timeline_order
                WHERE event_kind='{kind}' AND event_id=OLD.id;
            END"""
        )

    # Legacy records have no shared timestamps. Backfill deterministic order;
    # repeat migrations must preserve the order already assigned to records.
    selections = [
        f"SELECT match_id,minute,id AS event_id,'{kind}' AS event_kind FROM {table}"
        for table, kind in sources
    ]
    conn.execute(
        """INSERT INTO match_timeline_order (match_id,event_kind,event_id)
        SELECT old.match_id,old.event_kind,old.event_id FROM ("""
        + " UNION ALL ".join(selections)
        + """) AS old WHERE NOT EXISTS (
            SELECT 1 FROM match_timeline_order existing
            WHERE existing.event_kind=old.event_kind AND existing.event_id=old.event_id
        ) ORDER BY old.match_id,old.minute,old.event_kind,old.event_id"""
    )
