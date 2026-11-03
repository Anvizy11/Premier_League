"""Stable project paths, independent of the current working directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DATABASE_PATH = PROJECT_ROOT / "premier_league.db"
SESSION_KEY_PATH = PROJECT_ROOT / ".session_key"
