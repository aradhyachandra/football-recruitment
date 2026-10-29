-- Gate 1. Population: players with a transfermarkt appearance in one of the four leagues in the
-- 2015/16 season window (independent of the valuations, so the gate is not circular).
-- For each: is there a valuation in [date - N months, date] (usable: no hindsight), and in
-- [date - N months, date + N months] (either side, for context)?
WITH league_players AS (
    SELECT DISTINCT competition_id AS league, player_id
    FROM tm_appearances
    WHERE competition_id IN (SELECT unnest($leagues::VARCHAR[]))
      AND date BETWEEN $season_start::DATE AND $season_end::DATE
),
vals AS (
    SELECT player_id,
           bool_or(date BETWEEN $valuation_date::DATE - to_months($months)
                            AND $valuation_date::DATE) AS has_before,
           bool_or(date BETWEEN $valuation_date::DATE - to_months($months)
                            AND $valuation_date::DATE + to_months($months)) AS has_either
    FROM tm_player_valuations
    GROUP BY player_id
),
joined AS (
    SELECT lp.league, lp.player_id,
           coalesce(v.has_before, false) AS has_before,
           coalesce(v.has_either, false) AS has_either
    FROM league_players lp LEFT JOIN vals v USING (player_id)
)
SELECT league,
       COUNT(DISTINCT player_id) AS players,
       COUNT(DISTINCT player_id) FILTER (WHERE has_before) AS with_valuation_before,
       COUNT(DISTINCT player_id) FILTER (WHERE has_either) AS with_valuation_either_side
FROM joined
GROUP BY GROUPING SETS ((league), ())
ORDER BY league NULLS LAST;   -- the last row (league NULL) is all four leagues together
