-- Percentiles of each profile metric within each role pool (players at or above the threshold).
-- Summaries only: no per-player rows leave this query.
SELECT p.role, s.metric, s.kind, count(*) AS players,
       quantile_cont(s.value, $percentiles::DOUBLE[]) AS value_q,
       quantile_cont(s.value_padj, $percentiles::DOUBLE[]) AS value_padj_q
FROM r2_player_season s JOIN r2_players p USING (player_id)
WHERE p.minutes >= $threshold
GROUP BY p.role, s.metric, s.kind
ORDER BY p.role, s.metric;
