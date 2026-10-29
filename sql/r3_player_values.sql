-- R3 joined table: one row per player with an R2 profile, matched or not. Price = the latest
-- Transfermarkt valuation ON OR BEFORE $valuation_date (never a later one: no hindsight), with its
-- date and the gap in days; a gap above $max_gap_days is flagged as stale, not dropped. Age is at the
-- valuation date from the Transfermarkt date of birth.
CREATE OR REPLACE TABLE r3_player_values AS
WITH v AS (
    SELECT player_id, max(date) AS valuation_date, arg_max(market_value_in_eur, date) AS market_value_eur
    FROM tm_player_valuations
    WHERE date <= $valuation_date::DATE AND market_value_in_eur IS NOT NULL
    GROUP BY player_id
),
pl AS (
    SELECT player_id, count(*) FILTER (WHERE tm_all_apps > 0) AS clubs_with_appearances,
           bool_or(gap_flag) AS plausibility_flag
    FROM r3_plausibility GROUP BY player_id
)
SELECT p.player_id, s.display_name AS statsbomb_name, p.minutes, p.matches, p.n_teams,
       p.main_competition_id, p.role,
       m.status, m.method, m.score, m.transfermarkt_player_id, tp.name AS transfermarkt_name,
       m.best_candidate_id, m.best_candidate_name, m.best_score, m.second_score, m.n_candidates,
       tp.date_of_birth,
       date_sub('year', tp.date_of_birth, $valuation_date::DATE) AS age,
       ($valuation_date::DATE - tp.date_of_birth) / 365.25 AS age_years,
       v.market_value_eur, v.valuation_date,
       $valuation_date::DATE - v.valuation_date AS valuation_gap_days,
       CASE WHEN v.valuation_date IS NOT NULL
            THEN $valuation_date::DATE - v.valuation_date > $max_gap_days END AS valuation_stale,
       pl.clubs_with_appearances, pl.plausibility_flag
FROM r2_players p
JOIN r3_sb_players s USING (player_id)
JOIN r3_matches m ON m.statsbomb_player_id = p.player_id
LEFT JOIN tm_players tp ON tp.player_id = m.transfermarkt_player_id
LEFT JOIN v ON v.player_id = m.transfermarkt_player_id
LEFT JOIN pl ON pl.player_id = p.player_id
ORDER BY p.player_id;
