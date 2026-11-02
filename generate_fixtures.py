import random
from database import db_connection

def generate_gameweek_one():
    with db_connection() as conn:
        cursor = conn.cursor()

        # Проверяем, есть ли уже запланированные матчи 1-го тура
        existing = cursor.execute(
            "SELECT COUNT(*) AS cnt FROM matches WHERE gameweek = 1 AND status = 'SCHEDULED';"
        ).fetchone()

        if existing["cnt"] > 0:
            print(f"В 1-м туре уже создано {existing['cnt']} запланированных матчей.")
            return

        # Получаем все 20 клубов
        teams = cursor.execute("SELECT id, name FROM teams ORDER BY id ASC;").fetchall()
        team_ids = [t["id"] for t in teams]

        if len(team_ids) != 20:
            print(f"Ошибка: найдено {len(team_ids)} клубов вместо 20.")
            return

        random.seed(42)  # Фиксируем сид для воспроизводимости пар
        random.shuffle(team_ids)

        # Разбиваем 20 команд на 10 пар (хозяева - гости)
        fixtures_count = 0
        for i in range(0, len(team_ids), 2):
            home_id = team_ids[i]
            away_id = team_ids[i + 1]

            cursor.execute("""
                INSERT INTO matches (gameweek, home_team_id, away_team_id, status, is_finished)
                VALUES (1, ?, ?, 'SCHEDULED', 0)
            """, (home_id, away_id))
            fixtures_count += 1

        print(f"Успешно создано {fixtures_count} матчей для 1-го тура со статусом SCHEDULED!")

if __name__ == "__main__":
    generate_gameweek_one()