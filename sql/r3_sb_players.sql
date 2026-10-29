-- R3: the name forms of every player with an R2 profile row. StatsBomb can spell one player_id in
-- more than one way (for example "N''Golo Kanté" and "N'Golo Kanté"), so every spelling is kept.
-- display_name (nickname if there is one, else the full name; most frequent spelling) is for outputs.
CREATE OR REPLACE TABLE r3_sb_players AS
SELECT p.player_id,
       coalesce(mode(lp.player_nickname), mode(lp.player_name)) AS display_name,
       coalesce(list(DISTINCT lp.player_name) FILTER (WHERE lp.player_name IS NOT NULL), []) AS names,
       coalesce(list(DISTINCT lp.player_nickname) FILTER (WHERE lp.player_nickname IS NOT NULL), []) AS nicknames,
       coalesce(list(DISTINCT lp.country_name) FILTER (WHERE lp.country_name IS NOT NULL), []) AS countries,
       list_transform(any_value(p.teams), t -> t.team_id) AS team_ids
FROM r2_players p
JOIN sb_lineup_players lp ON lp.player_id = p.player_id
GROUP BY p.player_id;
