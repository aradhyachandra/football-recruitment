"""Hand-made tables for the R3 tests (club map, name matching, plausibility, valuations).

StatsBomb teams -> Transfermarkt clubs:
  1 "Alpha" (Premier League, 2) -> 101 (GB1);  2 "Beta" (Premier League) -> 102;  3 "Gamma" (Ligue 1, 7) -> 103 (FR1)
Each team plays on the dates in DATES; each Transfermarkt club has league appearances on the same dates.

StatsBomb players and the expected result:
  11 "N''Golo Kanté" / nickname "N'Golo Kanté" (doubled apostrophe)   -> 1001 "N'Golo Kanté", exact
  12 "José Ignacio Fernández Iglesias" / "Nacho" (full legal name)   -> 1002 "Nacho Fernández", word subset
  13 "Mateo Kovačić" (accent)                                         -> 1003 "Mateo Kovacic", exact
  14 "Mamadou Sakho" (France) and 15 "Mamadou Sako" (Senegal): similar names at one club; each is exact
     for one candidate and a close spelling of the other, so country decides -> 1004 and 1005
  16 "Jonathan Silva Ramos": "Jonathan" (1006) and "Silva" (1007) both one-word subsets, same country
     -> ambiguous, left unmatched
  17 "Jean-Michaël Seri" (hyphen, Gamma)                               -> 1009 "Jean Michael Seri", exact
  18 "Rémy Cabella": mid-season mover, Beta (4 matches) then Gamma (3) -> 1008, appearances at both clubs
  19 "Totally Different": no similar name in the squad               -> unmatched, low score
  20 "Carlos Henrique Casimiro" (no nickname here)                    -> 1010 "Casemiro" only by override
Valuations (date 2016-07-01): 1001 has 2016-06-01 (20m) and 2016-08-01 (30m, after the date: ignored);
1002 only 2015-01-01 (gap 547 days, stale but kept); 1003 only 2016-09-01 (after: no price).
Plausibility: player 12 played 5 StatsBomb matches but has 1 Transfermarkt league appearance -> flagged.
"""
from recruit import config, load

DATES = ["2015-08-08", "2015-08-15", "2015-08-22", "2015-08-29", "2015-09-12"]
TEAMS = {1: ("Alpha", 2), 2: ("Beta", 2), 3: ("Gamma", 7)}
CLUB_MAP = {"clubs": [
    {"competition_id": 2, "statsbomb_team_id": 1, "statsbomb_name": "Alpha", "transfermarkt_club_id": 101,
     "transfermarkt_name": "Alpha FC"},
    {"competition_id": 2, "statsbomb_team_id": 2, "statsbomb_name": "Beta", "transfermarkt_club_id": 102,
     "transfermarkt_name": "Beta FC"},
    {"competition_id": 7, "statsbomb_team_id": 3, "statsbomb_name": "Gamma", "transfermarkt_club_id": 103,
     "transfermarkt_name": "Gamma FC"},
]}
SCOPE = {
    "season": {"season_id": 27},
    "competitions": [{"competition_id": 2, "name": "Premier League", "transfermarkt_id": "GB1"},
                     {"competition_id": 7, "name": "Ligue 1", "transfermarkt_id": "FR1"}],
    "season_window": {"start": "2015-07-01", "end": "2016-06-30"},
    "valuation_date": "2016-07-01",
    "departing_player_ids": {"statsbomb_player_id": 11, "transfermarkt_player_id": 1001},
}
CLUB_LEAGUE = {101: "GB1", 102: "GB1", 103: "FR1"}

# StatsBomb: player_id -> (names, nickname, country, [(team_id, matches)], role)
SB = {
    11: (["N''Golo Kanté", "N'Golo Kanté"], "N'Golo Kanté", "France", [(1, 5)], "Central midfielder"),
    12: (["José Ignacio Fernández Iglesias"], "Nacho", "Spain", [(1, 5)], "Centre-back"),
    13: (["Mateo Kovačić"], None, "Croatia", [(1, 4)], "Central midfielder"),
    14: (["Mamadou Sakho"], None, "France", [(1, 5)], "Centre-back"),
    15: (["Mamadou Sako"], None, "Senegal", [(1, 2)], "Forward"),
    16: (["Jonathan Silva Ramos"], None, "Argentina", [(1, 3)], "Full-back"),
    17: (["Jean-Michaël Seri"], None, "Côte d'Ivoire", [(3, 5)], "Central midfielder"),
    18: (["Rémy Cabella"], None, "France", [(2, 4), (3, 3)], "Attacking midfielder"),
    19: (["Totally Different"], None, "Spain", [(1, 1)], "Forward"),
    20: (["Carlos Henrique Casimiro"], None, "Brazil", [(1, 5)], "Central midfielder"),
}
# Transfermarkt: player_id -> (name, first, last, citizenship, birth country, dob, {club: league apps})
TM = {
    1001: ("N'Golo Kanté", "N'Golo", "Kanté", "France", "France", "1991-03-29", {101: 5}),
    1002: ("Nacho Fernández", "Nacho", "Fernández", "Spain", "Spain", "1990-01-18", {101: 1}),
    1003: ("Mateo Kovacic", "Mateo", "Kovacic", "Croatia", "Austria", "1994-05-06", {101: 4}),
    1004: ("Mamadou Sakho", "Mamadou", "Sakho", "France", "France", "1990-02-13", {101: 5}),
    1005: ("Mamadou Sako", "Mamadou", "Sako", "Senegal", "Senegal", "1995-11-02", {101: 2}),
    1006: ("Jonathan", None, "Jonathan", "Argentina", "Argentina", "1993-01-01", {101: 3}),
    1007: ("Silva", None, "Silva", "Argentina", "Argentina", "1992-01-01", {101: 3}),
    1008: ("Rémy Cabella", "Rémy", "Cabella", "France", "France", "1990-03-08", {102: 4, 103: 3}),
    1009: ("Jean Michael Seri", "Jean Michael", "Seri", "Cote d'Ivoire", "Cote d'Ivoire", "1991-07-19", {103: 5}),
    1010: ("Casemiro", None, "Casemiro", "Brazil", "Brazil", "1992-02-23", {101: 5}),
    1011: ("Someone Else", "Someone", "Else", "England", "England", "1996-01-01", {101: 1}),
    1099: ("N'Golo Kanté", "N'Golo", "Kanté", "France", "France", "1980-01-01", {}),  # not at any club
}
VALUATIONS = [  # player_id, date, value
    (1001, "2016-06-01", 20_000_000), (1001, "2016-08-01", 30_000_000), (1001, "2015-10-14", 5_000_000),
    (1002, "2015-01-01", 8_000_000), (1003, "2016-09-01", 15_000_000),
    (1004, "2016-03-01", 18_000_000), (1008, "2016-02-01", 9_000_000),
]
OVERRIDES = {"overrides": [{"statsbomb_player_id": 20, "transfermarkt_player_id": 1010,
                            "statsbomb_name": "Carlos Henrique Casimiro", "transfermarkt_name": "Casemiro",
                            "reason": "legal name vs one-word playing name", "evidence": "test"}]}


def build(con) -> None:
    fields = config.load("statsbomb_fields")
    for table in ("sb_matches", "sb_lineup_players"):
        _, kind, keys = load.SB_TABLES[table]
        con.execute(load.create_sql(table, fields[kind], keys))
    con.execute((config.SQL_DIR / "r1_tm_tables.sql").read_text(encoding="utf-8"))

    match_id, matches, team_match = 0, [], {}
    for team, (name, comp) in TEAMS.items():
        for d in DATES:
            match_id += 1
            matches.append((match_id, comp, d, team, name))
            team_match[(team, d)] = match_id
    con.executemany("INSERT INTO sb_matches (match_id, competition_id, match_date, home_team_id, home_team_name) "
                    "VALUES (?, ?, ?, ?, ?)", matches)

    lineups, r2 = [], []
    for pid, (names, nick, country, teams, role) in SB.items():
        n_match = 0
        for team, n in teams:
            for i in range(n):
                lineups.append((team_match[(team, DATES[i])], TEAMS[team][1], team, TEAMS[team][0], pid,
                                names[(n_match + i) % len(names)], nick, country))
            n_match += n
        team_structs = [{"team_id": t, "competition_id": TEAMS[t][1], "minutes": 90.0 * n, "matches": n}
                        for t, n in teams]
        r2.append((pid, 90.0 * n_match, n_match, len(teams), team_structs, TEAMS[teams[0][0]][1], role))
    con.executemany("INSERT INTO sb_lineup_players (match_id, competition_id, team_id, team_name, player_id, "
                    "player_name, player_nickname, country_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lineups)
    con.execute("""CREATE TABLE r2_players (player_id BIGINT, minutes DOUBLE, matches BIGINT, n_teams BIGINT,
                   teams STRUCT(team_id BIGINT, competition_id INTEGER, minutes DOUBLE, matches BIGINT)[],
                   main_competition_id INTEGER, role VARCHAR)""")
    con.executemany("INSERT INTO r2_players VALUES (?, ?, ?, ?, ?, ?, ?)", r2)

    players, apps = [], []
    for pid, (name, first, last, cit, birth, dob, clubs) in TM.items():
        players.append((pid, first, last, name, cit, birth, dob))
        for club, n in clubs.items():
            for i in range(n):
                apps.append((f"{pid}_{club}_{i}", club * 1000 + i, pid, club, DATES[i], name, CLUB_LEAGUE[club]))
            # a cup game (not a league appearance) for every club member
            apps.append((f"{pid}_{club}_cup", club * 1000 + 99, pid, club, "2016-01-09", name, "FAC"))
    # a game outside the season window does not make 1011 a squad member of Gamma
    apps.append(("1011_103_old", 103999, 1011, 103, "2014-09-01", "Someone Else", "FR1"))
    con.executemany("INSERT INTO tm_players (player_id, first_name, last_name, name, country_of_citizenship, "
                    "country_of_birth, date_of_birth) VALUES (?, ?, ?, ?, ?, ?, ?)", players)
    con.executemany("INSERT INTO tm_appearances (appearance_id, game_id, player_id, player_club_id, date, "
                    "player_name, competition_id) VALUES (?, ?, ?, ?, ?, ?, ?)", apps)
    con.executemany("INSERT INTO tm_player_valuations (player_id, date, market_value_in_eur) VALUES (?, ?, ?)",
                    VALUATIONS)
