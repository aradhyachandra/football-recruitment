-- R2 step 1: the event columns R2 needs, with time in seconds and derived flags.
-- ts_s is time within the period (StatsBomb timestamp HH:MM:SS.mmm). `flags` lists every flag that is
-- true for the event; metric definitions (config/metrics.yaml -> r2_metric_defs) test against it.
-- bad_timestamp: the timestamp is more than $max_backward_seconds earlier than the latest earlier event
-- of the same period in StatsBomb's event order (index); such events are left out of all timing.
-- Parameters come from config/metrics.yaml (flags) and config/profiles.yaml (timing, excluded types).
CREATE OR REPLACE TABLE r2_events AS
WITH e0 AS (
    SELECT index, match_id, competition_id, period, possession, possession_team_id, team_id, player_id,
           type_name, subtype_name, outcome_name, shot_xg, duration,
           location_x, location_y, end_x, end_y,
           pass_shot_assist, pass_goal_assist, ball_recovery_failure,
           CAST(split_part(timestamp, ':', 1) AS INTEGER) * 3600
             + CAST(split_part(timestamp, ':', 2) AS INTEGER) * 60
             + CAST(split_part(timestamp, ':', 3) AS DOUBLE) AS ts_s,
           row_number() OVER () AS event_key
    FROM sb_events
    WHERE competition_id IN (SELECT unnest($competition_ids::INTEGER[]))
),
e AS (
    SELECT *,
           coalesce(max(ts_s) OVER (PARTITION BY match_id, period ORDER BY index
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) - ts_s
                    > $max_backward_seconds, false) AS bad_timestamp
    FROM e0
),
-- start of each possession sequence (play events only), for pressure regains
seq_start AS (
    SELECT match_id, period, possession, any_value(possession_team_id) AS team_id, min(ts_s) AS start_s
    FROM e
    WHERE NOT list_contains($excluded_event_types::VARCHAR[], type_name) AND NOT bad_timestamp
    GROUP BY match_id, period, possession
),
regain AS (
    SELECT DISTINCT p.event_key
    FROM e p
    JOIN seq_start s
      ON s.match_id = p.match_id AND s.period = p.period AND s.team_id = p.team_id
     AND s.possession > p.possession
     AND s.start_s >= p.ts_s AND s.start_s <= p.ts_s + $regain_seconds
    WHERE p.type_name = 'Pressure' AND NOT p.bad_timestamp
),
geo AS (
    SELECT e.*,
           sqrt(power(120 - location_x, 2) + power(40 - location_y, 2)) AS start_dist,
           sqrt(power(120 - end_x, 2) + power(40 - end_y, 2)) AS end_dist,
           (type_name = 'Carry'
            OR (type_name = 'Pass' AND NOT list_contains($pass_excluded_subtypes::VARCHAR[],
                                                         coalesce(subtype_name, '')))) AS open_play_move
    FROM e
)
SELECT g.match_id, g.competition_id, g.period, g.ts_s, g.duration, g.possession, g.possession_team_id,
       g.team_id, g.player_id, g.type_name, g.subtype_name, g.outcome_name, g.shot_xg, g.bad_timestamp,
       list_filter([
           CASE WHEN g.open_play_move
                 AND g.end_dist <= (1 - $min_share_closer) * g.start_dist
                 AND g.start_dist - g.end_dist >= $min_distance THEN 'progressive' END,
           CASE WHEN g.open_play_move AND g.type_name = 'Pass'
                 AND g.location_x < $final_third_x AND g.end_x >= $final_third_x THEN 'into_final_third' END,
           CASE WHEN r.event_key IS NOT NULL THEN 'pressure_regain' END,
           CASE WHEN g.pass_shot_assist OR g.pass_goal_assist THEN 'key_pass' END,
           CASE WHEN g.ball_recovery_failure THEN 'ball_recovery_failure' END
       ], x -> x IS NOT NULL) AS flags
FROM geo g
LEFT JOIN regain r USING (event_key);
