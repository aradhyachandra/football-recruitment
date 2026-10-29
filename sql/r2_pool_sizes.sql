-- Players at or above each minutes threshold, by role and main league (league with most minutes).
WITH th AS (SELECT unnest($thresholds::INTEGER[]) AS threshold)
SELECT th.threshold, p.role, p.main_competition_id AS competition_id, count(*) AS players
FROM th JOIN r2_players p ON p.minutes >= th.threshold
GROUP BY ALL
ORDER BY th.threshold, p.role, competition_id;
