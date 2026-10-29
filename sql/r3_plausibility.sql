-- R3 plausibility: for every matched player and every team he played for, StatsBomb matches played
-- (R2: matches with minutes) against the Transfermarkt player's league appearances for the mapped
-- club in the season window. A gap above $max_gap matches is flagged (config/matching.yaml).
CREATE OR REPLACE TABLE r3_plausibility AS
WITH t AS (
    SELECT m.statsbomb_player_id AS player_id, m.transfermarkt_player_id, unnest(p.teams) AS team
    FROM r3_matches m JOIN r2_players p ON p.player_id = m.statsbomb_player_id
    WHERE m.transfermarkt_player_id IS NOT NULL
)
SELECT t.player_id, t.transfermarkt_player_id, t.team.team_id AS statsbomb_team_id,
       t.team.competition_id AS competition_id, t.team.matches AS sb_matches,
       coalesce(s.league_apps, 0) AS tm_league_apps, coalesce(s.all_apps, 0) AS tm_all_apps,
       abs(t.team.matches - coalesce(s.league_apps, 0)) > $max_gap AS gap_flag
FROM t
LEFT JOIN r3_squads s ON s.statsbomb_team_id = t.team.team_id
                     AND s.transfermarkt_player_id = t.transfermarkt_player_id;
