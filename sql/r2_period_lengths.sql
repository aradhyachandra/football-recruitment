-- R2 step 2: real length of each period (with added time) and the time elapsed before it.
-- Length = timestamp of the period's "Half End" event; if missing, the last event's end in the period.
CREATE OR REPLACE TABLE r2_period_lengths AS
WITH p AS (
    SELECT match_id, period,
           coalesce(max(ts_s) FILTER (WHERE type_name = 'Half End'),
                    max(ts_s + coalesce(duration, 0))) AS length_s,
           count(*) FILTER (WHERE type_name = 'Half End') = 0 AS length_from_last_event
    FROM r2_events
    GROUP BY match_id, period
)
SELECT match_id, period, length_s, length_from_last_event,
       coalesce(sum(length_s) OVER (PARTITION BY match_id ORDER BY period
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS offset_s,
       sum(length_s) OVER (PARTITION BY match_id) AS match_length_s
FROM p;
