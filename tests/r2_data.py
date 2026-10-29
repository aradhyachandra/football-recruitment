"""Hand-made StatsBomb-shaped tables for the R2 tests. Every expected number in test_profiles.py is
worked out by hand from the rows below (comments give the arithmetic).

Match 1 (Premier League, competition 2): team 10 ("A") v team 20 ("B").
  Period 1 lasts 45:30 (2730 s), period 2 lasts 48:00 (2880 s): 5610 s = 93.5 minutes.
  Possession sequences (in-play time = first event start to last event end):
    1 A  0.0 -> 7.0   = 7.0      2 B 10.0 -> 12.5 = 2.5     3 A 14.0 -> 17.5 = 3.5
    4 B 30.0 -> 33.0  = 3.0      5 A 40.0 -> 44.5 = 4.5     (period 2) 6 B 0.0 -> 3.0 = 3.0
    7 A 10.0 -> 12.0  = 2.0
  A = 17.0 s, B = 8.5 s: A share 2/3, B share 1/3 (Half Start/End events are left out, and so is a
  Ball Receipt with a glitched timestamp of 0:00.5 placed after the penalty in event order, which
  would otherwise stretch sequence 5 to 0.5 -> 44.5 s).
  Passes: A 4, B 3, so A's pass share is 4/7.
Match 2 (Ligue 1, competition 7): team 30 v team 40, two 45:00 halves (90 minutes).
  Player 2 has moved from team 10 to team 30. Team 30 share 6/8 = 0.75.
"""
from recruit import config, load

A, B = 10, 20


def _ts(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"00:{int(m):02d}:{s:06.3f}"


def ev(match, period, t, poss, poss_team, team, player, type_name, dur=0.0, order=None, **kw):
    """One event; `order` places it in StatsBomb's event order (index) when that differs from time."""
    return {"_order": t if order is None else order, "match_id": match, "competition_id": 2 if match == 1 else 7, "period": period,
            "timestamp": _ts(t), "minute": int(t // 60) + (45 if period == 2 else 0),
            "second": int(t % 60), "type_name": type_name, "possession": poss,
            "possession_team_id": poss_team, "team_id": team, "player_id": player, "duration": dur, **kw}


def _half_marks(match, teams, lengths, last_poss):
    rows = []
    for period, length in enumerate(lengths, 1):
        for team in teams:
            rows.append(ev(match, period, 0, last_poss[period - 1][0], last_poss[period - 1][1], team, None,
                           "Half Start", order=-1))
            rows.append(ev(match, period, length, last_poss[period - 1][2], last_poss[period - 1][3], team,
                           None, "Half End"))
    return rows


def events() -> list[dict]:
    p = 2  # the departing player in these tests
    m1 = [
        # possession 1, A: progressive pass into the final third, then a progressive carry
        ev(1, 1, 0.0, 1, A, A, p, "Pass", 2.0, location_x=60.0, location_y=40.0, end_x=90.0, end_y=40.0),
        ev(1, 1, 3.0, 1, A, A, p, "Carry", 4.0, location_x=90.0, location_y=40.0, end_x=100.0, end_y=40.0),
        # possession 2, B: B passes, p presses (regain: A's next sequence starts 3.5 s later), intercepts
        ev(1, 1, 10.0, 2, B, B, 21, "Pass", 1.0, outcome_name="Incomplete", location_x=50.0,
           location_y=40.0, end_x=60.0, end_y=40.0),
        ev(1, 1, 10.5, 2, B, A, p, "Pressure", 1.5),
        ev(1, 1, 12.5, 2, B, A, p, "Interception", 0.0, outcome_name="Lost Out"),
        # possession 3, A: recovery, progressive key pass (not into the final third), shot by player 3
        ev(1, 1, 14.0, 3, A, A, p, "Ball Recovery", 0.0),
        ev(1, 1, 15.0, 3, A, A, p, "Pass", 1.5, location_x=100.0, location_y=30.0, end_x=110.0, end_y=40.0,
           pass_shot_assist=True),
        ev(1, 1, 17.0, 3, A, A, 3, "Shot", 0.5, subtype_name="Open Play", shot_xg=0.3),
        # possession 4, B: goal kick; p presses (no regain: A's next sequence is 9 s later), wins a tackle
        ev(1, 1, 30.0, 4, B, B, 22, "Pass", 2.0, subtype_name="Goal Kick", location_x=6.0, location_y=40.0,
           end_x=50.0, end_y=40.0),
        ev(1, 1, 31.0, 4, B, A, p, "Pressure", 1.0),
        ev(1, 1, 33.0, 4, B, A, p, "Duel", 0.0, subtype_name="Tackle", outcome_name="Won"),
        # possession 5, A: throw-in (completed, never progressive), injury clearance (not an attempt),
        # penalty by player 3 (not in shots or npxG)
        ev(1, 1, 40.0, 5, A, A, p, "Pass", 1.0, subtype_name="Throw-in", location_x=70.0, location_y=0.0,
           end_x=85.0, end_y=30.0),
        ev(1, 1, 42.0, 5, A, A, p, "Pass", 1.0, outcome_name="Injury Clearance", location_x=50.0,
           location_y=40.0, end_x=50.0, end_y=80.0),
        ev(1, 1, 44.0, 5, A, A, 3, "Shot", 0.5, subtype_name="Penalty", shot_xg=0.76),
        # glitched timestamp (0:00.5) on an event that comes last in the half's event order
        ev(1, 1, 0.5, 5, A, A, 8, "Ball Receipt*", None, order=44.1),
        # period 2, possession 6, B: p fouls, loses a tackle, blocks
        ev(1, 2, 0.0, 6, B, B, 21, "Pass", 3.0, location_x=60.0, location_y=40.0, end_x=70.0, end_y=40.0),
        ev(1, 2, 2.0, 6, B, A, p, "Foul Committed", 0.0),
        ev(1, 2, 2.5, 6, B, A, p, "Duel", 0.0, subtype_name="Tackle", outcome_name="Lost In Play"),
        ev(1, 2, 3.0, 6, B, A, p, "Block", 0.0),
        # possession 7, A: one dribble won, one lost, a failed recovery
        ev(1, 2, 10.0, 7, A, A, p, "Dribble", 0.5, outcome_name="Complete"),
        ev(1, 2, 11.0, 7, A, A, p, "Dribble", 0.5, outcome_name="Incomplete"),
        ev(1, 2, 12.0, 7, A, A, p, "Ball Recovery", 0.0, ball_recovery_failure=True),
    ]
    m1 += _half_marks(1, [A, B], [2730.0, 2880.0], [(1, A, 5, A), (6, B, 7, A)])
    m2 = [
        ev(2, 1, 0.0, 1, 30, 30, p, "Pass", 6.0, location_x=60.0, location_y=40.0, end_x=62.0, end_y=40.0),
        ev(2, 1, 10.0, 2, 40, 40, 41, "Pass", 2.0, location_x=60.0, location_y=40.0, end_x=62.0, end_y=40.0),
        ev(2, 1, 11.0, 2, 40, 30, p, "Duel", 0.0, subtype_name="Tackle", outcome_name="Success In Play"),
    ]
    m2 += _half_marks(2, [30, 40], [2700.0, 2700.0], [(1, 30, 2, 40), (2, 40, 2, 40)])
    rows = sorted(m1 + m2, key=lambda r: (r["match_id"], r["period"], r["_order"]))
    for i, r in enumerate(rows):
        r["index"] = i + 1
        del r["_order"]
    return rows


def _stint(match, team, player, pos, frm, to, from_period, to_period, end="Final Whistle"):
    return {"match_id": match, "competition_id": 2 if match == 1 else 7, "team_id": team,
            "player_id": player, "position_id": pos, "from_time": frm, "to_time": to,
            "from_period": from_period, "to_period": to_period, "end_reason": end}


def stints() -> list[dict]:
    s = _stint
    rows = [
        s(1, A, 1, 1, "00:00", None, 1, None),                                    # 93.5
        s(1, A, 2, 13, "00:00", "70:00", 1, 2, "Tactical Shift"),                 # 70.5 (2730 + 1500 s)
        s(1, A, 2, 10, "70:00", None, 2, None),                                   # 23.0
        s(1, A, 3, 23, "00:00", "60:00", 1, 2, "Substitution - Off (Tactical)"),  # 60.5
        s(1, A, 4, 23, "60:00", None, 2, None),                                   # 33.0
        s(1, A, 5, 4, "00:00", "30:00", 1, 1, "Foul Committed (Red Card)"),       # 30.0
        s(1, A, 6, 6, "00:00", "45:00", 1, 2, "Substitution - Off (Tactical)"),   # half-time: 45.5
        s(1, A, 7, 6, "45:00", None, 2, None),                                    # 48.0
        s(1, A, 8, 15, "00:00", "20:00", 1, 1, "Player Off"),                     # 20.0
        s(1, A, 8, 15, "23:00", None, 1, None),                                   # 70.5 -> 90.5 in all
        s(1, A, 9, 21, "00:00", "46:10", 1, 1, "Substitution - Off (Injury)"),    # clock past 45:30: 45.5
        s(1, A, 12, 21, "46:10", None, 1, None),                                  # 48.0
        s(1, A, 13, 14, "00:00", None, 1, None),
        s(1, A, 14, 3, "00:00", None, 1, None),
        s(1, A, 15, 12, "00:00", None, 1, None),
        s(1, A, 16, 22, "00:00", None, 1, None),
    ]
    b_positions = [10, 1, 3, 5, 2, 6, 13, 16, 12, 23, 19]
    rows += [s(1, B, 21 + i, pos, "00:00", None, 1, None) for i, pos in enumerate(b_positions)]
    rows += [s(2, 30, 2, 16, "00:00", None, 1, None), s(2, 40, 41, 10, "00:00", None, 1, None)]
    return rows


MATCHES = [{"match_id": 1, "competition_id": 2, "season_id": 27},
           {"match_id": 2, "competition_id": 7, "season_id": 27}]


def build(con) -> None:
    """Create the sb_* tables with the real column types and fill them with the rows above."""
    fields = config.load("statsbomb_fields")
    for table, (_, kind, keys) in load.SB_TABLES.items():
        con.execute(load.create_sql(table, fields[kind], keys))
    for table, rows in [("sb_events", events()), ("sb_lineup_positions", stints()),
                        ("sb_matches", MATCHES)]:
        cols = sorted({k for r in rows for k in r})
        con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        [[r.get(c) for c in cols] for r in rows])
    # booleans default to false in the real flatten step; match that here
    for col in ("pass_shot_assist", "pass_goal_assist", "ball_recovery_failure"):
        con.execute(f"UPDATE sb_events SET {col} = false WHERE {col} IS NULL")
