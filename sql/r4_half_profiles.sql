-- R4 split-half profiles: one row per player, half and metric. Half 1 = matches dated before
-- $split_date, half 2 = on or after it. Per-90 values are season totals for that half / minutes * 90,
-- the same arithmetic as r2_player_season (raw, and possession-adjusted for the adjusted metrics);
-- pass completion is completed / attempted passes in that half. passes_attempted only feeds the ratio.
CREATE OR REPLACE TABLE r4_half_profiles AS
WITH pm AS (
    SELECT pm.*, CASE WHEN m.match_date < $split_date::DATE THEN 1 ELSE 2 END AS half
    FROM r2_player_match pm JOIN sb_matches m USING (match_id)
),
mins AS (   -- one row per player-match carries minutes on every metric row: take it once per match
    SELECT player_id, half, sum(minutes) AS minutes
    FROM (SELECT DISTINCT match_id, player_id, half, minutes FROM pm)
    GROUP BY player_id, half
),
tot AS (
    SELECT player_id, half, metric, bool_or(possession_adjusted) AS padj,
           sum(raw) AS raw, sum(adjusted) AS adjusted
    FROM pm GROUP BY player_id, half, metric
)
SELECT t.player_id, t.half, m.minutes, t.metric,
       t.raw / m.minutes * 90 AS value,
       CASE WHEN t.padj THEN t.adjusted / m.minutes * 90 END AS value_padj
FROM tot t JOIN mins m USING (player_id, half)
WHERE t.metric <> 'passes_attempted' AND m.minutes > 0
UNION ALL
SELECT c.player_id, c.half, m.minutes, 'pass_completion' AS metric,
       c.raw / NULLIF(a.raw, 0) AS value, NULL AS value_padj
FROM tot c
JOIN tot a ON a.player_id = c.player_id AND a.half = c.half AND a.metric = 'passes_attempted'
JOIN mins m ON m.player_id = c.player_id AND m.half = c.half
WHERE c.metric = 'passes_completed' AND m.minutes > 0
ORDER BY player_id, half, metric;
