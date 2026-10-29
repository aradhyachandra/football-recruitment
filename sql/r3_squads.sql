-- R3 candidate squads: every Transfermarkt player with an appearance (any competition) for a mapped
-- club inside the season window, with his league and all-competition appearance counts for that club.
-- The name matching compares a StatsBomb player only with the squads of his own team(s).
CREATE OR REPLACE TABLE r3_squads AS
SELECT cm.statsbomb_team_id, a.player_id AS transfermarkt_player_id,
       count(DISTINCT a.game_id) FILTER (WHERE a.competition_id = cm.transfermarkt_competition_id) AS league_apps,
       count(DISTINCT a.game_id) AS all_apps,
       coalesce(any_value(p.name), any_value(a.player_name)) AS name,
       any_value(p.first_name) AS first_name, any_value(p.last_name) AS last_name,
       any_value(p.country_of_citizenship) AS country_of_citizenship,
       any_value(p.country_of_birth) AS country_of_birth
FROM r3_club_map cm
JOIN tm_appearances a ON a.player_club_id = cm.transfermarkt_club_id
                     AND a.date BETWEEN $season_start::DATE AND $season_end::DATE
LEFT JOIN tm_players p ON p.player_id = a.player_id
GROUP BY cm.statsbomb_team_id, a.player_id;
