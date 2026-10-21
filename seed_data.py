from database import get_connection

TEAMS = [
    ("Arsenal", "ARS", "Emirates Stadium", "London", "Mikel", "Arteta", "Spain"),
    ("Aston Villa", "AVL", "Villa Park", "Birmingham", "Unai", "Emery", "Spain"),
    ("Bournemouth", "BOU", "Vitality Stadium", "Bournemouth", "Andoni", "Iraola", "Spain"),
    ("Brentford", "BRE", "Gtech Community Stadium", "London", "Thomas", "Frank", "Denmark"),
    ("Brighton & Hove Albion", "BHA", "Amex Stadium", "Brighton", "Fabian", "Hürzeler", "Germany"),
    ("Chelsea", "CHE", "Stamford Bridge", "London", "Enzo", "Maresca", "Italy"),
    ("Crystal Palace", "CRY", "Selhurst Park", "London", "Oliver", "Glasner", "Austria"),
    ("Everton", "EVE", "Goodison Park", "Liverpool", "Sean", "Dyche", "England"),
    ("Fulham", "FUL", "Craven Cottage", "London", "Marco", "Silva", "Portugal"),
    ("Ipswich Town", "IPS", "Portman Road", "Ipswich", "Kieran", "McKenna", "Northern Ireland"),
    ("Leicester City", "LEI", "King Power Stadium", "Leicester", "Steve", "Cooper", "Wales"),
    ("Liverpool", "LIV", "Anfield", "Liverpool", "Arne", "Slot", "Netherlands"),
    ("Manchester City", "MCI", "Etihad Stadium", "Manchester", "Pep", "Guardiola", "Spain"),
    ("Manchester United", "MUN", "Old Trafford", "Manchester", "Erik", "ten Hag", "Netherlands"),
    ("Newcastle United", "NEW", "St James' Park", "Newcastle", "Eddie", "Howe", "England"),
    ("Nottingham Forest", "NFO", "City Ground", "Nottingham", "Nuno", "Espírito Santo", "Portugal"),
    ("Southampton", "SOU", "St Mary's Stadium", "Southampton", "Russell", "Martin", "Scotland"),
    ("Tottenham Hotspur", "TOT", "Tottenham Hotspur Stadium", "London", "Ange", "Postecoglou", "Australia"),
    ("West Ham United", "WHU", "London Stadium", "London", "Julen", "Lopetegui", "Spain"),
    ("Wolverhampton Wanderers", "WOL", "Molineux Stadium", "Wolverhampton", "Gary", "O'Neil", "England")
]

SAMPLE_PLAYERS = [
    # (Team Short Name, First Name, Last Name, Number, Position, Nationality, Birth Date)
    ("ARS", "Martin", "Ødegaard", 8, "MF", "Norway", "1998-12-17"),
    ("ARS", "Bukayo", "Saka", 7, "FW", "England", "2001-09-05"),
    ("ARS", "Declan", "Rice", 41, "MF", "England", "1999-01-14"),
    ("MCI", "Erling", "Haaland", 9, "FW", "Norway", "2000-07-21"),
    ("MCI", "Kevin", "De Bruyne", 17, "MF", "Belgium", "1991-06-28"),
    ("MCI", "Rodri", "Hernandez", 16, "MF", "Spain", "1996-06-22"),
    ("LIV", "Mohamed", "Salah", 11, "FW", "Egypt", "1992-06-15"),
    ("LIV", "Virgil", "van Dijk", 4, "DF", "Netherlands", "1991-07-08"),
    ("CHE", "Cole", "Palmer", 20, "MF", "England", "2002-05-06"),
    ("MUN", "Bruno", "Fernandes", 8, "MF", "Portugal", "1994-09-08"),
    ("TOT", "Son", "Heung-min", 7, "FW", "South Korea", "1992-07-08"),
    ("AVL", "Ollie", "Watkins", 11, "FW", "England", "1995-12-30"),
    ("NEW", "Alexander", "Isak", 14, "FW", "Sweden", "1999-09-21")
]

def seed():
    conn = get_connection()
    cursor = conn.cursor()

    print("Заполнение клубов и тренеров...")
    team_ids = {}
    for name, short_name, stadium, city, coach_fn, coach_ln, coach_nat in TEAMS:
        cursor.execute("""
            INSERT OR IGNORE INTO teams (name, short_name, stadium, city)
            VALUES (?, ?, ?, ?)
        """, (name, short_name, stadium, city))
        
        cursor.execute("SELECT id FROM teams WHERE short_name = ?", (short_name,))
        team_id = cursor.fetchone()["id"]
        team_ids[short_name] = team_id

        # Добавляем главного тренера в штаб
        cursor.execute("""
            INSERT INTO staff (team_id, first_name, last_name, role, nationality)
            VALUES (?, ?, ?, 'Head Coach', ?)
        """, (team_id, coach_fn, coach_ln, coach_nat))

    print("Заполнение ключевых игроков...")
    for short_name, fn, ln, number, pos, nat, bdate in SAMPLE_PLAYERS:
        t_id = team_ids.get(short_name)
        if t_id:
            cursor.execute("""
                INSERT INTO players (team_id, first_name, last_name, jersey_number, position, nationality, birth_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (t_id, fn, ln, number, pos, nat, bdate))

    conn.commit()
    conn.close()
    print(" 20 клубов, главные тренеры и базовые игроки успешно добавлены в базу!")

if __name__ == "__main__":
    seed()
