import sqlite3

DB_NAME = "premier_league.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Таблица команд
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        short_name TEXT NOT NULL,
        stadium TEXT NOT NULL,
        city TEXT NOT NULL,
        logo_url TEXT
    );
    """)

    # 2. Таблица игроков
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        jersey_number INTEGER NOT NULL,
        position TEXT NOT NULL CHECK(position IN ('GK', 'DF', 'MF', 'FW')),
        nationality TEXT NOT NULL,
        birth_date TEXT,
        is_suspended BOOLEAN DEFAULT 0,
        FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
    );
    """)

    # 3. Таблица тренеров и персонала
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        role TEXT NOT NULL,
        nationality TEXT NOT NULL,
        FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
    );
    """)

    # 4. Таблица матчей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gameweek INTEGER NOT NULL,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        home_score INTEGER DEFAULT NULL,
        away_score INTEGER DEFAULT NULL,
        is_finished BOOLEAN DEFAULT 0,
        FOREIGN KEY (home_team_id) REFERENCES teams(id),
        FOREIGN KEY (away_team_id) REFERENCES teams(id)
    );
    """)

    # 5. Протоколы матчей (события: голы, карточки)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS match_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        minute INTEGER NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('GOAL', 'PENALTY', 'YELLOW_CARD', 'RED_CARD')),
        FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
        FOREIGN KEY (team_id) REFERENCES teams(id),
        FOREIGN KEY (player_id) REFERENCES players(id)
    );
    """)

    conn.commit()
    conn.close()
    print("База данных premier_league.db и таблицы успешно созданы!")

if __name__ == "__main__":
    init_db()
