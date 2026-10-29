-- How closely the in-play-time share (used) and the pass share (check) agree, per team-match.
SELECT count(*) AS team_matches,
       avg(abs(in_play_share - pass_share)) AS mean_abs_diff,
       quantile_cont(abs(in_play_share - pass_share), 0.5) AS median_abs_diff,
       quantile_cont(abs(in_play_share - pass_share), 0.95) AS p95_abs_diff,
       max(abs(in_play_share - pass_share)) AS max_abs_diff,
       corr(in_play_share, pass_share) AS correlation,
       min(in_play_share) AS min_in_play_share,
       max(in_play_share) AS max_in_play_share,
       count(*) FILTER (WHERE in_play_share IS NULL) AS missing_share
FROM r2_team_possession;
