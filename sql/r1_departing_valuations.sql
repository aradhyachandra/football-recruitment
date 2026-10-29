-- The departing player's valuations within N months either side of the valuation date (context only:
-- rows after the date are shown in the audit but never used as a price). usable = on or before the
-- date and inside the gate window, the same rule as r1_valuation_gate.sql.
SELECT date, market_value_in_eur, current_club_name,
       $valuation_date::DATE - date AS days_before,
       date BETWEEN $valuation_date::DATE - to_months($window_months)
                AND $valuation_date::DATE AS usable
FROM tm_player_valuations
WHERE player_id = $player_id
  AND date BETWEEN $valuation_date::DATE - to_months($months)
               AND $valuation_date::DATE + to_months($months)
ORDER BY date;
