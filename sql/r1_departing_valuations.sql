-- The departing player's valuations in the N months up to the valuation date. Nothing dated after the
-- date is read (no hindsight in public results). usable = inside the gate window, the same rule as
-- r1_valuation_gate.sql.
SELECT date, market_value_in_eur, current_club_name,
       $valuation_date::DATE - date AS days_before,
       date >= $valuation_date::DATE - to_months($window_months) AS usable
FROM tm_player_valuations
WHERE player_id = $player_id
  AND date BETWEEN $valuation_date::DATE - to_months($months) AND $valuation_date::DATE
ORDER BY date;
