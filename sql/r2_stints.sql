-- R2 step 3: minutes for every lineup position spell, with its role bucket.
-- A match-clock time (MM:SS, restarting at 45:00 in period 2) becomes elapsed match seconds:
--   offset of its period + (clock - the period's clock start), kept between 0 and the period length.
-- An open-ended spell (no "to" time) runs to the final whistle, added time included.
CREATE OR REPLACE TABLE r2_stints AS
WITH s AS (
    SELECT l.match_id, l.competition_id, l.team_id, l.player_id, l.position_id,
           l.from_time, l.to_time, l.from_period, l.end_reason,
           coalesce(l.to_period, l.from_period) AS to_period,
           CAST(split_part(l.from_time, ':', 1) AS INTEGER) * 60
             + CAST(split_part(l.from_time, ':', 2) AS INTEGER) AS from_clock_s,
           CAST(split_part(l.to_time, ':', 1) AS INTEGER) * 60
             + CAST(split_part(l.to_time, ':', 2) AS INTEGER) AS to_clock_s
    FROM sb_lineup_positions l
    WHERE l.competition_id IN (SELECT unnest($competition_ids::INTEGER[]))
),
t AS (
    SELECT s.*,
           pf.offset_s + least(greatest(s.from_clock_s - list_extract($clock_starts::INTEGER[], s.from_period),
                                        0), pf.length_s) AS start_s,
           CASE WHEN s.to_time IS NULL THEN pf.match_length_s
                ELSE pt.offset_s + least(greatest(s.to_clock_s
                                                  - list_extract($clock_starts::INTEGER[], s.to_period), 0),
                                         pt.length_s) END AS end_s
    FROM s
    JOIN r2_period_lengths pf ON pf.match_id = s.match_id AND pf.period = s.from_period
    LEFT JOIN r2_period_lengths pt ON pt.match_id = s.match_id AND pt.period = s.to_period
)
SELECT t.match_id, t.competition_id, t.team_id, t.player_id, t.position_id, r.role, t.from_time,
       t.to_time, t.from_period, t.to_period, t.end_reason, t.start_s, t.end_s,
       greatest(t.end_s - t.start_s, 0) / 60.0 AS minutes
FROM t
LEFT JOIN r2_roles r USING (position_id);
