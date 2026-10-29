-- The departing player's per-90 values and his percent_rank within his role pool (players in the same
-- role at or above the threshold; he is included in the pool even if he were below it).
WITH me AS (SELECT role FROM r2_players WHERE player_id = $player_id),
pool AS (
    SELECT p.player_id FROM r2_players p, me
    WHERE p.role = me.role AND (p.minutes >= $threshold OR p.player_id = $player_id)
),
ranked AS (
    SELECT s.player_id, s.metric, s.kind, s.total_raw, s.total_adjusted, s.value, s.value_padj,
           percent_rank() OVER (PARTITION BY s.metric ORDER BY s.value) AS pct_rank,
           percent_rank() OVER (PARTITION BY s.metric ORDER BY s.value_padj) AS pct_rank_padj,
           count(*) OVER (PARTITION BY s.metric) AS pool_size
    FROM r2_player_season s JOIN pool USING (player_id)
)
SELECT metric, kind, total_raw, total_adjusted, value, value_padj, pct_rank,
       CASE WHEN value_padj IS NOT NULL THEN pct_rank_padj END AS pct_rank_padj, pool_size
FROM ranked WHERE player_id = $player_id
ORDER BY metric;
