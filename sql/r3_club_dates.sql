-- R3 check on config/club_map.yaml: for every StatsBomb team in the data, how many of its league
-- match dates have a Transfermarkt league appearance for the mapped club on the same date.
-- A team missing from the map shows with a NULL club (run_r3 stops on it).
WITH sb AS (
    SELECT DISTINCT lp.team_id, m.competition_id, m.match_id, m.match_date
    FROM sb_lineup_players lp JOIN sb_matches m USING (match_id)
),
tm_dates AS (
    SELECT DISTINCT cm.statsbomb_team_id, a.date
    FROM r3_club_map cm
    JOIN tm_appearances a ON a.player_club_id = cm.transfermarkt_club_id
                         AND a.competition_id = cm.transfermarkt_competition_id
)
SELECT sb.team_id AS statsbomb_team_id, any_value(sb.competition_id) AS competition_id,
       any_value(cm.transfermarkt_club_id) AS transfermarkt_club_id,
       count(DISTINCT sb.match_id) AS sb_matches,
       count(DISTINCT sb.match_id) FILTER (WHERE d.date IS NOT NULL) AS dates_covered
FROM sb
LEFT JOIN r3_club_map cm ON cm.statsbomb_team_id = sb.team_id
LEFT JOIN tm_dates d ON d.statsbomb_team_id = sb.team_id AND d.date = sb.match_date
GROUP BY sb.team_id
ORDER BY sb.team_id;
