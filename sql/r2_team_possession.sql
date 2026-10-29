-- R2 step 4: each team's possession share per match, two ways.
-- in_play_share (used): share of in-play time in the team's possession sequences; a sequence's
--   in-play time runs from its first event's start to its last event's end, within one period
--   (events with a bad timestamp, see r2_events.sql, are left out of the timing).
-- pass_share (check only): share of the match's pass attempts made by the team.
CREATE OR REPLACE TABLE r2_team_possession AS
WITH seq AS (
    SELECT match_id, period, possession, possession_team_id AS team_id,
           max(ts_s + coalesce(duration, 0)) - min(ts_s) AS seconds
    FROM r2_events
    WHERE NOT list_contains($excluded_event_types::VARCHAR[], type_name) AND NOT bad_timestamp
    GROUP BY match_id, period, possession, possession_team_id
),
in_play AS (SELECT match_id, team_id, sum(seconds) AS seconds FROM seq GROUP BY match_id, team_id),
passes AS (
    SELECT match_id, team_id, count(*) AS passes FROM r2_events WHERE type_name = 'Pass'
    GROUP BY match_id, team_id
),
teams AS (SELECT DISTINCT match_id, competition_id, team_id FROM r2_stints)
SELECT t.match_id, t.competition_id, t.team_id,
       coalesce(i.seconds, 0) AS in_play_seconds,
       coalesce(i.seconds, 0) / sum(coalesce(i.seconds, 0)) OVER (PARTITION BY t.match_id) AS in_play_share,
       coalesce(p.passes, 0) AS passes,
       coalesce(p.passes, 0) / sum(coalesce(p.passes, 0)) OVER (PARTITION BY t.match_id) AS pass_share
FROM teams t
LEFT JOIN in_play i USING (match_id, team_id)
LEFT JOIN passes p USING (match_id, team_id);
