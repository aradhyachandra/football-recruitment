-- Gate 2: pressure events per league, and how many matches have at least one.
SELECT m.competition_id,
       COUNT(DISTINCT m.match_id) AS matches,
       COUNT(e.event_id) AS pressure_events,
       COUNT(DISTINCT e.match_id) AS matches_with_pressure
FROM sb_matches m
LEFT JOIN sb_events e ON e.match_id = m.match_id AND e.type_name = $event_type
WHERE m.competition_id IN (SELECT unnest($competition_ids::INTEGER[]))
GROUP BY m.competition_id
ORDER BY m.competition_id;
