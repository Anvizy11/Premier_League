"""SQLite connections and transaction boundaries."""

import os
import sqlite3
from contextlib import contextmanager

from premier_league.paths import DATABASE_PATH

DATABASE_NAME = str(DATABASE_PATH)


def get_connection():
    conn = sqlite3.connect(os.environ.get("PREMIER_LEAGUE_DATABASE", DATABASE_NAME), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_connection(write=False):
    conn = get_connection()
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
