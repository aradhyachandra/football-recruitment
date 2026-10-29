-- Event counts by type and league (aggregate counts only; no event rows leave the database).
SELECT type_name, competition_id, COUNT(*) AS n
FROM sb_events
GROUP BY type_name, competition_id;
