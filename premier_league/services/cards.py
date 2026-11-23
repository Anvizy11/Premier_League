"""Season card totals, independent of whether suspensions have been served."""


def get_card_statistics(conn):
    statistics = {"player": {}, "staff": {}, "team": {}}
    for table, subject_field, kind in (
        ("match_events", "player_id", "player"),
        ("staff_events", "staff_id", "staff"),
    ):
        rows = conn.execute(
            f"""SELECT e.{subject_field} AS subject_id,e.team_id,e.match_id,
                SUM(CASE WHEN e.event_type='YELLOW_CARD' THEN 1 ELSE 0 END) AS yellows,
                SUM(CASE WHEN e.event_type='RED_CARD' THEN 1 ELSE 0 END) AS direct_reds
            FROM {table} e JOIN matches m ON m.id=e.match_id
            WHERE m.status='VERIFIED' AND e.event_type IN ('YELLOW_CARD','RED_CARD')
            GROUP BY e.{subject_field},e.team_id,e.match_id"""
        ).fetchall()
        for row in rows:
            second_yellow_dismissal = row["yellows"] >= 2
            yellow_cards = 0 if second_yellow_dismissal else row["yellows"]
            red_cards = row["direct_reds"] + int(second_yellow_dismissal)
            for group, identity in ((kind, row["subject_id"]), ("team", row["team_id"])):
                totals = statistics[group].setdefault(identity, {"yellow_cards": 0, "red_cards": 0})
                totals["yellow_cards"] += yellow_cards
                totals["red_cards"] += red_cards
    return statistics
