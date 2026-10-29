"""R3 name matching (pure Python) on hand-made names. Squad and country rules are in r3_data.py."""
import pytest

from recruit import config, matching
from tests import r3_data

CFG = config.load("matching")


@pytest.mark.parametrize("raw, expected", [
    ("N''Golo Kanté", "ngolo kante"),       # StatsBomb's doubled apostrophe
    ("N'Golo Kanté", "ngolo kante"),
    ("N’Golo Kante", "ngolo kante"),   # typographic apostrophe
    ('David N"Gog', "david ngog"),         # double quote used as an apostrophe
    ("Jean-Michaël Seri", "jean michael seri"),
    ("Martin Ødegaard", "martin odegaard"),  # ø is not an accent in Unicode terms
    ("  Mesut   ÖZIL ", "mesut ozil"),
    ("Mateo Kovačić", "mateo kovacic"),
    ("Filip Đorđević", "filip djordjevic"),  # Serbian đ is written dj in Latin transliteration
    (None, ""),
])
def test_normalise(raw, expected):
    assert matching.normalise(raw, CFG) == expected


def sb(names, nickname=None, country=None):
    return {"names": names, "nicknames": [nickname] if nickname else [], "countries": [country] if country else []}


def tm(name, first=None, last=None, countries=()):
    return {"name": name, "first_name": first, "last_name": last, "countries": list(countries)}


def test_score_exact_full_name_and_nickname():
    assert matching.score(sb(["Mateo Kovačić"]), tm("Mateo Kovacic"), CFG) == (1.0, "exact_name")
    assert matching.score(sb(["Carlos Henrique Casimiro"], "Casemiro"), tm("Casemiro"), CFG) == (1.0, "exact_nickname")
    # Transfermarkt first + last name counts as a name form too
    assert matching.score(sb(["Luka Modric"]), tm("Modrić", "Luka", "Modrić"), CFG) == (1.0, "exact_name")


def test_score_full_legal_name_vs_short_name():
    s = sb(["José Ignacio Fernández Iglesias"], "Nacho")
    assert matching.score(s, tm("Nacho Fernández"), CFG) == (0.95, "token_subset")
    assert matching.score(sb(["Marcelo Vieira da Silva Júnior"]), tm("Marcelo"), CFG) == (0.88, "token_subset")


def test_score_short_first_name_with_same_surname():
    assert matching.score(sb(["Robert Brady"]), tm("Robbie Brady"), CFG) == (0.87, "token_prefix")
    assert matching.score(sb(["Alexandre Dimitri Song-Billong"]), tm("Alex Song"), CFG) == (0.87, "token_prefix")
    # first names sharing fewer than three letters are not enough
    assert matching.score(sb(["Thomas Robson"]), tm("Tommy Robson"), CFG)[0] < CFG["min_score"]


def test_two_word_subset_beats_one_word_subset():
    player = {"player_id": 1, "names": ["Samuel García Sánchez"], "nicknames": ["Samu"], "countries": ["Spain"]}
    squad = [{"player_id": 7, "name": "Samu García", "countries": ["Spain"]},
             {"player_id": 8, "name": "Samu Castillejo", "countries": ["Spain"]}]
    r = matching.match_one(player, squad, CFG)
    assert (r["transfermarkt_player_id"], r["method"]) == (7, "token_subset")


def test_score_fuzzy_spelling_and_low_score():
    score, method = matching.score(sb(["Aleksandar Mitrović"]), tm("Aleksander Mitrovic"), CFG)
    assert method == "fuzzy" and 0.9 < score < 1.0
    score, _ = matching.score(sb(["Totally Different"]), tm("Someone Else"), CFG)
    assert score < CFG["min_score"]


def _players():
    out = []
    for pid, (names, nick, country, teams, role) in r3_data.SB.items():
        out.append({"player_id": pid, "names": names, "nicknames": [nick] if nick else [],
                    "countries": [country], "team_ids": [t for t, _ in teams]})
    return out


def _squads():
    squads = {}
    team_of_club = {c["transfermarkt_club_id"]: c["statsbomb_team_id"] for c in r3_data.CLUB_MAP["clubs"]}
    for pid, (name, first, last, cit, birth, dob, clubs) in r3_data.TM.items():
        for club in clubs:
            squads.setdefault(team_of_club[club], []).append(
                {"player_id": pid, "name": name, "first_name": first, "last_name": last, "countries": [cit, birth]})
    return squads


@pytest.fixture(scope="module")
def result():
    rows = matching.match_players(_players(), _squads(), r3_data.OVERRIDES["overrides"], CFG)
    return {r["statsbomb_player_id"]: r for r in rows}


@pytest.mark.parametrize("sb_id, tm_id, method", [
    (11, 1001, "exact_name"),        # doubled apostrophe; the other "N'Golo Kanté" (1099) is at no club
    (12, 1002, "token_subset"),      # full legal name vs short name
    (13, 1003, "exact_name"),        # accent
    (14, 1004, "exact_name+country"),  # similar names at one club, country decides
    (15, 1005, "exact_name+country"),
    (17, 1009, "exact_name"),        # hyphen
    (18, 1008, "exact_name"),        # mid-season mover: candidates from both clubs
    (20, 1010, "override"),
])
def test_match_players(result, sb_id, tm_id, method):
    assert result[sb_id]["transfermarkt_player_id"] == tm_id
    assert result[sb_id]["method"] == method
    assert result[sb_id]["status"] == "matched"


def test_ambiguous_and_low_score_are_left_unmatched(result):
    assert result[16]["transfermarkt_player_id"] is None and result[16]["status"] == "ambiguous"
    assert result[16]["best_score"] == 0.88                      # kept for review
    assert result[19]["transfermarkt_player_id"] is None and result[19]["status"] == "low_score"


def test_casemiro_needs_the_override():
    rows = matching.match_players(_players(), _squads(), [], CFG)
    row = next(r for r in rows if r["statsbomb_player_id"] == 20)
    assert row["transfermarkt_player_id"] is None


def test_override_to_unmatched_and_typo_guard():
    forced = [{"statsbomb_player_id": 11, "transfermarkt_player_id": None, "reason": "r", "evidence": "e"}]
    rows = matching.match_players(_players(), _squads(), forced, CFG)
    row = next(r for r in rows if r["statsbomb_player_id"] == 11)
    assert row["transfermarkt_player_id"] is None and row["status"] == "override_unmatched"
    typo = [{"statsbomb_player_id": 11, "transfermarkt_player_id": 1099, "reason": "r", "evidence": "e"}]
    with pytest.raises(ValueError, match="not in the squad"):
        matching.match_players(_players(), _squads(), typo, CFG)
    outside = [{"statsbomb_player_id": 11, "transfermarkt_player_id": 1099, "outside_squad": True,
                "reason": "r", "evidence": "e"}]   # e.g. a season missing from Transfermarkt appearances
    row = next(r for r in matching.match_players(_players(), _squads(), outside, CFG) if r["statsbomb_player_id"] == 11)
    assert (row["transfermarkt_player_id"], row["method"]) == (1099, "override")
    no_reason = [{"statsbomb_player_id": 11, "transfermarkt_player_id": 1001}]
    with pytest.raises(ValueError, match="reason"):
        matching.match_players(_players(), _squads(), no_reason, CFG)


def test_one_transfermarkt_player_is_not_given_to_two_statsbomb_players():
    players = _players() + [{"player_id": 99, "names": ["N'Golo Kanté"], "nicknames": [], "countries": ["France"],
                             "team_ids": [1]}]
    rows = {r["statsbomb_player_id"]: r for r in matching.match_players(players, _squads(), [], CFG)}
    assert rows[11]["transfermarkt_player_id"] is None and rows[99]["transfermarkt_player_id"] is None
    assert rows[11]["status"] == rows[99]["status"] == "ambiguous_shared"


def test_real_override_and_club_map_files_are_well_formed():
    overrides = config.load("player_overrides")["overrides"]
    ids = [o["statsbomb_player_id"] for o in overrides]
    assert len(ids) == len(set(ids))
    for o in overrides:
        assert o.get("reason") and o.get("evidence"), o


def test_all_80_teams_map_exactly_once():
    clubs = config.load("club_map")["clubs"]
    scope = config.load("scope")
    assert len(clubs) == 80
    assert len({c["statsbomb_team_id"] for c in clubs}) == 80
    assert len({c["transfermarkt_club_id"] for c in clubs}) == 80
    for comp in config.competition_ids(scope):
        assert sum(c["competition_id"] == comp for c in clubs) == 20
