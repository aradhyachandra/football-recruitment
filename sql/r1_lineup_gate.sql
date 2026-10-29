-- Gate 3: lineup position stints carry start (from) and end (to) times. An empty "to" means the
-- player stayed on until the final whistle; the open-ended rows are broken down separately.
WITH team_match AS (
    SELECT match_id, team_id, COUNT(DISTINCT player_id) AS players
    FROM sb_lineup_positions GROUP BY match_id, team_id
)
SELECT
    (SELECT COUNT(*) FROM sb_lineup_positions) AS position_rows,
    (SELECT COUNT(*) FROM sb_lineup_positions WHERE from_time IS NOT NULL) AS with_from_time,
    (SELECT COUNT(*) FROM sb_lineup_positions WHERE to_time IS NOT NULL) AS with_to_time,
    (SELECT COUNT(*) FROM sb_lineup_positions WHERE from_period IS NOT NULL) AS with_from_period,
    (SELECT COUNT(*) FROM sb_matches) AS matches,
    (SELECT COUNT(*) FROM (SELECT match_id FROM team_match GROUP BY match_id
                           HAVING COUNT(*) = 2)) AS matches_with_both_teams,
    (SELECT MIN(players) FROM team_match) AS min_players_per_team_match,
    (SELECT MAX(players) FROM team_match) AS max_players_per_team_match;
