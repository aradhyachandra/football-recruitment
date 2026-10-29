-- R2 step 6: one row per player for the season (all clubs and leagues in scope summed).
-- r2_player_teams: minutes per team; r2_player_roles: minutes per role bucket;
-- r2_players: totals, role (most minutes; ties go to the role listed first in roles.yaml), share of
--   minutes in it, main league (most minutes), and whether he played for more than one team;
-- r2_player_season: per-90 value of each metric (raw and possession-adjusted) and the ratios.
CREATE OR REPLACE TABLE r2_player_teams AS
SELECT player_id, team_id, competition_id, sum(minutes) AS minutes, count(DISTINCT match_id) AS matches
FROM r2_stints GROUP BY player_id, team_id, competition_id;

CREATE OR REPLACE TABLE r2_player_roles AS
SELECT s.player_id, s.role, any_value(r.role_order) AS role_order, sum(s.minutes) AS minutes
FROM r2_stints s JOIN (SELECT DISTINCT role, role_order FROM r2_roles) r USING (role)
GROUP BY s.player_id, s.role;

CREATE OR REPLACE TABLE r2_players AS
WITH tot AS (
    SELECT player_id, sum(minutes) AS minutes, sum(matches) AS matches, count(*) AS n_teams,
           count(DISTINCT competition_id) AS n_leagues,
           list({'team_id': team_id, 'competition_id': competition_id, 'minutes': minutes,
                 'matches': matches} ORDER BY minutes DESC) AS teams,
           arg_max(competition_id, minutes) AS main_competition_id
    FROM r2_player_teams GROUP BY player_id
),
role AS (
    SELECT player_id, role, minutes AS role_minutes
    FROM (SELECT *, row_number() OVER (PARTITION BY player_id ORDER BY minutes DESC, role_order) AS rn
          FROM r2_player_roles)
    WHERE rn = 1
)
SELECT t.player_id, t.minutes, t.matches, t.n_teams, t.n_leagues, t.n_teams > 1 AS moved_mid_season,
       t.teams, t.main_competition_id, r.role, r.role_minutes / t.minutes AS role_share
FROM tot t JOIN role r USING (player_id);

CREATE OR REPLACE TABLE r2_player_season AS
WITH sums AS (
    SELECT player_id, metric, any_value(possession_adjusted) AS possession_adjusted,
           sum(raw) AS total_raw, sum(adjusted) AS total_adjusted
    FROM r2_player_match GROUP BY player_id, metric
),
rates AS (
    SELECT s.player_id, s.metric, 'per90' AS kind, s.total_raw, s.total_adjusted,
           s.total_raw * 90 / p.minutes AS value,
           s.total_adjusted * 90 / p.minutes AS value_padj
    FROM sums s JOIN r2_players p USING (player_id)
    JOIN r2_metric_defs d ON d.name = s.metric
    WHERE d.in_profile
),
ratios AS (
    SELECT n.player_id, r.name AS metric, 'ratio' AS kind, n.total_raw, NULL::DOUBLE AS total_adjusted,
           CASE WHEN m.total_raw > 0 THEN n.total_raw / m.total_raw END AS value,
           NULL::DOUBLE AS value_padj
    FROM r2_ratio_defs r
    JOIN sums n ON n.metric = r.numerator
    JOIN sums m ON m.metric = r.denominator AND m.player_id = n.player_id
)
SELECT * FROM rates UNION ALL SELECT * FROM ratios;
