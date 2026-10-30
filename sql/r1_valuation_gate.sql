-- Gate 1. Population: players with a transfermarkt appearance in one of the four leagues in the
-- 2015/16 season window (independent of the valuations, so the gate is not circular).
-- For each: is there a valuation in [date - N months, date] (usable: no hindsight)? Valuations after
-- the date are never read, not even for context.
WITH league_players AS (
    SELECT DISTINCT competition_id AS league, player_id
    FROM tm_appearances
    WHERE competition_id IN (SELECT unnest($leagues::VARCHAR[]))
      AND date BETWEEN $season_start::DATE AND $season_end::DATE
),
vals AS (
    SELECT player_id, true AS has_before
    FROM tm_player_valuations
    WHERE date BETWEEN $valuation_date::DATE - to_months($months) AND $valuation_date::DATE
    GROUP BY player_id
),
joined AS (
    SELECT lp.league, lp.player_id, coalesce(v.has_before, false) AS has_before
    FROM league_players lp LEFT JOIN vals v USING (player_id)
)
SELECT league,
       COUNT(DISTINCT player_id) AS players,
       COUNT(DISTINCT player_id) FILTER (WHERE has_before) AS with_valuation_before
FROM joined
GROUP BY GROUPING SETS ((league), ())
ORDER BY league NULLS LAST;   -- the last row (league NULL) is all four leagues together
