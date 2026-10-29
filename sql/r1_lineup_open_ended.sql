-- Stints with no end time, by end reason (expected: almost all "Final Whistle").
SELECT coalesce(end_reason, '(none)') AS end_reason, COUNT(*) AS rows
FROM sb_lineup_positions
WHERE to_time IS NULL
GROUP BY ALL
ORDER BY rows DESC, end_reason;
