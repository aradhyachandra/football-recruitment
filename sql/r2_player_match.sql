-- R2 step 5: one row per player, match, team and metric: raw count (or xG sum) and, for defensive
-- metrics, the possession-adjusted value  raw * $reference_share / opponent share  (per match).
-- An event counts for a metric when it passes every filter of that metric's row in r2_metric_defs.
CREATE OR REPLACE TABLE r2_player_match AS
WITH pm AS (
    SELECT match_id, competition_id, team_id, player_id, sum(minutes) AS minutes
    FROM r2_stints GROUP BY match_id, competition_id, team_id, player_id
),
counts AS (
    SELECT e.match_id, e.team_id, e.player_id, d.name AS metric,
           sum(CASE d.value WHEN 'count' THEN 1.0 WHEN 'shot_xg' THEN coalesce(e.shot_xg, 0) END) AS raw
    FROM r2_events e
    JOIN r2_metric_defs d
      ON e.type_name = d.event_type
     AND (d.subtypes IS NULL OR list_contains(d.subtypes, e.subtype_name))
     AND (d.exclude_subtypes IS NULL OR e.subtype_name IS NULL
          OR NOT list_contains(d.exclude_subtypes, e.subtype_name))
     AND (d.outcomes IS NULL OR list_contains(d.outcomes, e.outcome_name))
     AND (d.exclude_outcomes IS NULL OR e.outcome_name IS NULL
          OR NOT list_contains(d.exclude_outcomes, e.outcome_name))
     AND (NOT d.outcome_null OR e.outcome_name IS NULL)
     AND (d.flags_true IS NULL OR list_has_all(e.flags, d.flags_true))
     AND (d.flags_false IS NULL OR NOT list_has_any(e.flags, d.flags_false))
    WHERE e.player_id IS NOT NULL
    GROUP BY e.match_id, e.team_id, e.player_id, d.name
)
SELECT pm.match_id, pm.competition_id, pm.team_id, pm.player_id, pm.minutes, d.name AS metric,
       d.possession_adjusted, coalesce(c.raw, 0) AS raw, p.in_play_share AS team_share,
       1 - p.in_play_share AS opponent_share,
       CASE WHEN d.possession_adjusted
            THEN coalesce(c.raw, 0) * $reference_share / (1 - p.in_play_share) END AS adjusted
FROM pm
CROSS JOIN r2_metric_defs d
LEFT JOIN counts c ON c.match_id = pm.match_id AND c.team_id = pm.team_id
                  AND c.player_id = pm.player_id AND c.metric = d.name
LEFT JOIN r2_team_possession p ON p.match_id = pm.match_id AND p.team_id = pm.team_id;
