from database import db_connection

def run_protocol_test():
    with db_connection() as conn:
        cursor = conn.cursor()

        print("--- [1/4] Выбор команд для матча ---")
        chelsea = cursor.execute("SELECT id, name FROM teams WHERE short_name = 'CHE';").fetchone()
        arsenal = cursor.execute("SELECT id, name FROM teams WHERE short_name = 'ARS';").fetchone()

        if not chelsea or not arsenal:
            print("Ошибка: команды CHE или ARS не найдены в базе.")
            return

        che_id = chelsea["id"]
        ars_id = arsenal["id"]
        print(f"Матч: {chelsea['name']} (Хозяева) vs {arsenal['name']} (Гости)")

        # 1. Создаем матч 1-го тура с учетом реальных колонок
        cursor.execute("""
            INSERT INTO matches (gameweek, home_team_id, away_team_id, status, is_finished, referee_name)
            VALUES (1, ?, ?, 'PENDING', 0, 'Michael Oliver')
        """, (che_id, ars_id))
        match_id = cursor.lastrowid
        print(f"Матч #{match_id} создан со статусом PENDING.")

        # 2. Игроки для фиксации событий
        print("\n--- [2/4] Подготовка участников событий ---")
        palmer = cursor.execute("SELECT id FROM players WHERE team_id = ? AND last_name = 'Palmer';", (che_id,)).fetchone()
        saliba = cursor.execute("SELECT id FROM players WHERE team_id = ? AND last_name = 'Saliba';", (ars_id,)).fetchone()
        gyokeres = cursor.execute("SELECT id FROM players WHERE team_id = ? AND last_name = 'Gyökeres';", (ars_id,)).fetchone()

        # 3. Вносим события в match_events
        print("\n--- [3/4] Добавление событий матча ---")
        # 14' Гол Палмера (Челси) -> 1:0
        cursor.execute("""
            INSERT INTO match_events (match_id, team_id, player_id, event_type, minute)
            VALUES (?, ?, ?, 'GOAL', 14)
        """, (match_id, che_id, palmer["id"]))
        print("14' Гол: Cole Palmer (Chelsea) -> 1:0")

        # 38' Автогол Салиба (гол идет Челси) -> 2:0
        cursor.execute("""
            INSERT INTO match_events (match_id, team_id, player_id, event_type, minute)
            VALUES (?, ?, ?, 'OWN_GOAL', 38)
        """, (match_id, ars_id, saliba["id"]))
        print("38' Автогол: William Saliba (Arsenal) -> 2:0 в пользу Chelsea")

        # 71' Гол Дьокереша (Арсенал) -> 2:1
        cursor.execute("""
            INSERT INTO match_events (match_id, team_id, player_id, event_type, minute)
            VALUES (?, ?, ?, 'GOAL', 71)
        """, (match_id, ars_id, gyokeres["id"]))
        print("71' Гол: Viktor Gyökeres (Arsenal) -> 2:1")

        # 4. Верификация протокола и фиксация счета
        print("\n--- [4/4] Верификация протокола ---")
        cursor.execute("""
            SELECT 
                SUM(CASE 
                    WHEN (team_id = ? AND event_type = 'GOAL') OR (team_id = ? AND event_type = 'OWN_GOAL') 
                    THEN 1 ELSE 0 END) AS home_goals,
                SUM(CASE 
                    WHEN (team_id = ? AND event_type = 'GOAL') OR (team_id = ? AND event_type = 'OWN_GOAL') 
                    THEN 1 ELSE 0 END) AS away_goals
            FROM match_events
            WHERE match_id = ? AND event_type IN ('GOAL', 'OWN_GOAL');
        """, (che_id, ars_id, ars_id, che_id, match_id))

        scores = cursor.fetchone()
        home_score = scores["home_goals"] or 0
        away_score = scores["away_goals"] or 0

        # Обновляем матч: фиксируем счет, статус VERIFIED и завершенность
        cursor.execute("""
            UPDATE matches
            SET home_score = ?, away_score = ?, status = 'VERIFIED', is_finished = 1, verified_by = 'Chief Referee'
            WHERE id = ?
        """, (home_score, away_score, match_id))

        print(f"Результат верификации: {chelsea['name']} {home_score} : {away_score} {arsenal['name']}")
        
        if home_score == 2 and away_score == 1:
            print("\nПроверка пройдена успешно: автогол зачислен сопернику, матч помечен как VERIFIED.")

if __name__ == "__main__":
    run_protocol_test()