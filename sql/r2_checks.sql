-- Data checks reported with the profiles (counts only).
SELECT
    (SELECT count(*) FROM r2_players) AS players,
    (SELECT count(*) FROM r2_players WHERE moved_mid_season) AS movers,
    (SELECT count(*) FROM r2_players WHERE n_leagues > 1) AS movers_between_leagues,
    (SELECT count(*) FROM r2_players WHERE moved_mid_season AND minutes >= $threshold) AS movers_over_threshold,
    (SELECT count(*) FROM r2_stints WHERE role IS NULL) AS stints_without_role,
    (SELECT count(*) FROM r2_period_lengths WHERE length_from_last_event) AS periods_without_half_end,
    (SELECT max(period) FROM r2_period_lengths) AS max_period,
    (SELECT count(*) FROM r2_events e WHERE e.player_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM r2_stints s WHERE s.match_id = e.match_id AND s.player_id = e.player_id))
        AS events_without_stint,
    (SELECT count(*) FROM r2_events WHERE player_id IS NOT NULL) AS player_events,
    (SELECT count(*) FROM r2_events WHERE bad_timestamp) AS bad_timestamp_events,
    (SELECT min(1 - in_play_share) FROM r2_team_possession) AS min_opponent_share,
    (SELECT max(1 - in_play_share) FROM r2_team_possession) AS max_opponent_share;
