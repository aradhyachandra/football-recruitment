-- Matches, events, teams and players per league. "Played" = at least one lineup position stint.
WITH comps AS (SELECT unnest($competition_ids::INTEGER[]) AS competition_id)
SELECT
    c.competition_id,
    (SELECT COUNT(*) FROM sb_matches m WHERE m.competition_id = c.competition_id) AS matches,
    (SELECT COUNT(*) FROM sb_events e WHERE e.competition_id = c.competition_id) AS events,
    (SELECT COUNT(DISTINCT team_id) FROM sb_lineup_players p
      WHERE p.competition_id = c.competition_id) AS teams,
    (SELECT COUNT(DISTINCT player_id) FROM sb_lineup_players p
      WHERE p.competition_id = c.competition_id) AS squad_players,
    (SELECT COUNT(DISTINCT player_id) FROM sb_lineup_positions s
      WHERE s.competition_id = c.competition_id) AS players_who_played
FROM comps c
ORDER BY c.competition_id;
