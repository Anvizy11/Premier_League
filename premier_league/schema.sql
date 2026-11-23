CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        short_name TEXT NOT NULL,
        stadium TEXT NOT NULL,
        city TEXT NOT NULL,
        logo_url TEXT
    );
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
CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        role TEXT NOT NULL,
        birth_date TEXT,
        nationality TEXT NOT NULL, is_suspended BOOLEAN DEFAULT 0,
        FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
    );
CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gameweek INTEGER NOT NULL,
        home_team_id INTEGER NOT NULL,
        away_team_id INTEGER NOT NULL,
        home_score INTEGER DEFAULT NULL,
        away_score INTEGER DEFAULT NULL,
        is_finished BOOLEAN DEFAULT 0, status TEXT DEFAULT 'SCHEDULED', referee_name TEXT, verified_by TEXT,
        referee_user_id INTEGER REFERENCES users(id), assistant_one TEXT, assistant_two TEXT,
        fourth_official TEXT, match_date TEXT, var_official TEXT, avar_official TEXT,
        FOREIGN KEY (home_team_id) REFERENCES teams(id),
        FOREIGN KEY (away_team_id) REFERENCES teams(id)
    );
CREATE TABLE IF NOT EXISTS match_lineups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            is_captain INTEGER NOT NULL DEFAULT 0 CHECK(is_captain IN (0,1)),
            is_goalkeeper INTEGER CHECK(is_goalkeeper IN (0,1)),
            is_starter INTEGER DEFAULT 0,    -- 1: в старте, 0: на замене
            minute_in INTEGER DEFAULT 0,     -- минута выхода на поле (0 для старта)
            minute_out INTEGER DEFAULT 90,   -- минута ухода (90 по умолчанию или минута замены/удаления)
            minutes_played INTEGER DEFAULT 0,
            FOREIGN KEY (match_id) REFERENCES matches (id) ON DELETE CASCADE,
            FOREIGN KEY (player_id) REFERENCES players (id),
            FOREIGN KEY (team_id) REFERENCES teams (id),
            UNIQUE(match_id, player_id)
        );
CREATE TABLE IF NOT EXISTS match_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        minute INTEGER NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('GOAL', 'PENALTY', 'YELLOW_CARD', 'RED_CARD', 'OWN_GOAL')),
        FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
        FOREIGN KEY (team_id) REFERENCES teams(id),
        FOREIGN KEY (player_id) REFERENCES players(id)
    );
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('team_admin', 'referee', 'organizer')),
 team_id INTEGER REFERENCES teams(id),
 CHECK ((role = 'team_admin' AND team_id IS NOT NULL) OR (role != 'team_admin' AND team_id IS NULL))
);
CREATE TABLE IF NOT EXISTS match_substitutions (
 id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 player_out_id INTEGER NOT NULL REFERENCES players(id), player_in_id INTEGER NOT NULL REFERENCES players(id),
 minute INTEGER NOT NULL CHECK(minute BETWEEN 1 AND 90),
 UNIQUE(match_id, player_out_id), UNIQUE(match_id, player_in_id)
);

CREATE TABLE IF NOT EXISTS match_team_submissions (
 match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 team_id INTEGER NOT NULL REFERENCES teams(id),
 status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','SUBMITTED','APPROVED')),
 checked_by TEXT, PRIMARY KEY(match_id,team_id)
);
CREATE TABLE IF NOT EXISTS match_staff (
 match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 staff_id INTEGER NOT NULL REFERENCES staff(id), team_id INTEGER NOT NULL REFERENCES teams(id),
 role TEXT NOT NULL, PRIMARY KEY(match_id,staff_id)
);
CREATE TABLE IF NOT EXISTS staff_events (
 id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 staff_id INTEGER NOT NULL REFERENCES staff(id), team_id INTEGER NOT NULL REFERENCES teams(id),
 minute INTEGER NOT NULL CHECK(minute BETWEEN 1 AND 90),
 event_type TEXT NOT NULL CHECK(event_type IN ('YELLOW_CARD','RED_CARD'))
);
CREATE TABLE IF NOT EXISTS disciplinary_decisions (
 id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id),
 subject_type TEXT NOT NULL CHECK(subject_type IN ('player','staff')), subject_id INTEGER NOT NULL,
 reason TEXT NOT NULL CHECK(reason IN ('RED_CARD','SECOND_YELLOW','YELLOW_LIMIT')),
 total_games INTEGER NOT NULL CHECK(total_games >= 1), explanation TEXT NOT NULL,
 decided_by TEXT NOT NULL, UNIQUE(match_id,subject_type,subject_id,reason)
);
CREATE TABLE IF NOT EXISTS disciplinary_decision_history (
 id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES matches(id),
 subject_type TEXT NOT NULL CHECK(subject_type IN ('player','staff')), subject_id INTEGER NOT NULL,
 reason TEXT NOT NULL CHECK(reason IN ('RED_CARD','SECOND_YELLOW','YELLOW_LIMIT')),
 total_games INTEGER NOT NULL CHECK(total_games >= 1), served_games INTEGER NOT NULL CHECK(served_games >= 0),
 effective_after_match_id INTEGER NOT NULL REFERENCES matches(id),
 explanation TEXT NOT NULL, decided_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS protocol_confirmations (
 match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 scope TEXT NOT NULL, confirmed_by INTEGER NOT NULL REFERENCES users(id),
 content_hash TEXT NOT NULL, confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(match_id,scope)
);

CREATE TABLE IF NOT EXISTS officials (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, source_url TEXT
);

CREATE TABLE IF NOT EXISTS match_timeline_order (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
 event_kind TEXT NOT NULL CHECK(event_kind IN ('player','staff','substitution')),
 event_id INTEGER NOT NULL,
 UNIQUE(event_kind,event_id)
);
CREATE INDEX IF NOT EXISTS match_timeline_order_match ON match_timeline_order(match_id);

CREATE UNIQUE INDEX IF NOT EXISTS players_birth_identity
ON players(first_name COLLATE NOCASE,last_name COLLATE NOCASE,birth_date)
WHERE birth_date IS NOT NULL AND birth_date<>'';
CREATE UNIQUE INDEX IF NOT EXISTS staff_birth_identity
ON staff(first_name COLLATE NOCASE,last_name COLLATE NOCASE,birth_date)
WHERE birth_date IS NOT NULL AND birth_date<>'';
