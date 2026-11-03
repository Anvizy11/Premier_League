"""Sample PL officials; directory entries are not application login accounts."""
SOURCE = 'https://www.premierleague.com/en/news/4444029/match-officials-for-matchweek-9-in-premier-league-season-2025-26'
NAMES = ('Michael Oliver', 'Anthony Taylor', 'Chris Kavanagh', 'Stuart Attwell',
         'Andy Madley', 'Craig Pawson', 'Stuart Burt', 'Gary Beswick', 'Adam Nunn',
         'James Mainwaring', 'Wade Smith', 'Simon Bennett')


def seed_officials(conn):
    for name in NAMES:
        conn.execute('INSERT OR IGNORE INTO officials (name,source_url) VALUES (?,?)',(name,SOURCE))
    # Preserve manually entered names in earlier match protocols.
    for field in ('referee_name','assistant_one','assistant_two','fourth_official','var_official','avar_official'):
        for row in conn.execute(f'SELECT DISTINCT {field} FROM matches WHERE {field} IS NOT NULL'):
            if row[0].strip():
                conn.execute('INSERT OR IGNORE INTO officials (name) VALUES (?)',(row[0].strip(),))
