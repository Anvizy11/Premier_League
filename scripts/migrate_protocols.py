from premier_league.database import db_connection


def run_migration():
    with db_connection() as conn:
        cursor = conn.cursor()

        # 1. Создаем таблицу составов на конкретный матч (match_lineups)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS match_lineups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,
                is_starter INTEGER DEFAULT 0,    -- 1: в старте, 0: на замене
                minute_in INTEGER DEFAULT 0,     -- минута выхода на поле (0 для старта)
                minute_out INTEGER DEFAULT 90,   -- минута ухода (90 по умолчанию или минута замены/удаления)
                minutes_played INTEGER DEFAULT 0,
                FOREIGN KEY (match_id) REFERENCES matches (id) ON DELETE CASCADE,
                FOREIGN KEY (player_id) REFERENCES players (id),
                FOREIGN KEY (team_id) REFERENCES teams (id),
                UNIQUE(match_id, player_id)
            );
        """
        )

        # 2. Добавляем необходимые поля в таблицу matches, если их еще нет
        cursor.execute("PRAGMA table_info(matches);")
        columns = [col[1] for col in cursor.fetchall()]

        if "status" not in columns:
            cursor.execute("ALTER TABLE matches ADD COLUMN status TEXT DEFAULT 'SCHEDULED';")
            print("-> Добавлена колонка: status")

        if "referee_name" not in columns:
            cursor.execute("ALTER TABLE matches ADD COLUMN referee_name TEXT;")
            print("-> Добавлена колонка: referee_name")

        if "verified_by" not in columns:
            cursor.execute("ALTER TABLE matches ADD COLUMN verified_by TEXT;")
            print("-> Добавлена колонка: verified_by")

        # Приводим уже существующие матчи к статусу VERIFIED, если они были помечены завершенными
        cursor.execute(
            """
            UPDATE matches
            SET status = 'VERIFIED'
            WHERE is_finished = 1 AND (status IS NULL OR status = 'SCHEDULED');
        """
        )

    print("Миграция структуры под протоколы успешно завершена!")


if __name__ == "__main__":
    run_migration()
