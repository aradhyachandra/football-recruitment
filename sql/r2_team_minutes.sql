-- Sanity check: players' minutes per team per match against 11 x match length. Team-matches outside
-- the tolerance are split by whether a red card or a temporary "Player Off" spell explains them.
WITH tm AS (
    SELECT s.match_id, s.team_id, sum(s.minutes) AS minutes, any_value(l.match_length_s) / 60.0 AS match_minutes,
           bool_or(s.end_reason ILIKE '%red card%' OR s.end_reason ILIKE '%second yellow%') AS red_card,
           bool_or(s.end_reason ILIKE 'Player Off%' AND s.end_reason <> 'Player Off (Permanent)')
               AS player_off
    FROM r2_stints s
    JOIN (SELECT DISTINCT match_id, match_length_s FROM r2_period_lengths) l USING (match_id)
    GROUP BY s.match_id, s.team_id
),
r AS (SELECT *, minutes / (11 * match_minutes) AS ratio FROM tm)
SELECT count(*) AS team_matches,
       count(*) FILTER (WHERE abs(ratio - 1) <= $tolerance) AS within_tolerance,
       count(*) FILTER (WHERE ratio < 1 - $tolerance) AS below,
       count(*) FILTER (WHERE ratio < 1 - $tolerance AND red_card) AS below_with_red_card,
       count(*) FILTER (WHERE ratio < 1 - $tolerance AND NOT red_card AND player_off) AS below_with_player_off_only,
       count(*) FILTER (WHERE ratio < 1 - $tolerance AND NOT red_card AND NOT player_off) AS below_unexplained,
       count(*) FILTER (WHERE ratio > 1 + $tolerance) AS above,
       sum(minutes - 11 * match_minutes) FILTER (WHERE ratio > 1 + $tolerance) AS above_excess_minutes,
       sum(minutes) AS all_minutes,
       min(ratio) AS min_ratio, quantile_cont(ratio, 0.5) AS median_ratio, max(ratio) AS max_ratio,
       quantile_cont(match_minutes, 0.5) AS median_match_minutes,
       min(match_minutes) AS min_match_minutes, max(match_minutes) AS max_match_minutes
FROM r;
