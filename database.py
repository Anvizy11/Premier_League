import os
import sqlite3
from contextlib import contextmanager

DATABASE_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "premier_league.db")


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
