"""A single display timeline for goals, player/staff cards and substitutions."""


def get_recorded_order(conn, match_id):
    return {
        (row["event_kind"], row["event_id"]): row["id"]
        for row in conn.execute(
            "SELECT id,event_kind,event_id FROM match_timeline_order WHERE match_id=?",
            (match_id,),
        )
    }


def build_match_timeline(conn, match_id, events, staff_events, substitutions):
    recorded_order = get_recorded_order(conn, match_id)
    timeline = []
    for kind, records, delete_action in (
        ("player", events, "delete-event"),
        ("staff", staff_events, "delete-staff-event"),
        ("substitution", substitutions, "delete-substitution"),
    ):
        for record in records:
            timeline.append(
                dict(
                    record,
                    kind=kind,
                    delete_action=delete_action,
                    recorded_order=recorded_order[kind, record["id"]],
                )
            )

    return sorted(timeline, key=lambda item: (item["minute"], item["recorded_order"]))
