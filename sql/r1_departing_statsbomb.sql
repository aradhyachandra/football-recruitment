-- Find the departing player in the StatsBomb lineups by name (full name or nickname).
SELECT p.player_id, p.player_name, p.team_name,
       COUNT(DISTINCT p.match_id) AS matches_listed,
       COUNT(DISTINCT s.match_id) AS matches_played
FROM sb_lineup_players p
LEFT JOIN sb_lineup_positions s
       ON s.match_id = p.match_id AND s.player_id = p.player_id
WHERE p.player_name = $name OR p.player_nickname = $name
GROUP BY ALL
ORDER BY matches_listed DESC;
