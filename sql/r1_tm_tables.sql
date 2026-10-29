-- transfermarkt-datasets tables with explicit types. Only the columns later milestones need are
-- loaded. Today's (2026) market value, current club and contract are left out on purpose: using
-- them would be hindsight. Prices come only from tm_player_valuations up to the valuation date.
CREATE TABLE tm_players (
    player_id              BIGINT NOT NULL,
    first_name             VARCHAR,
    last_name              VARCHAR,
    name                   VARCHAR,
    player_code            VARCHAR,
    country_of_birth       VARCHAR,
    country_of_citizenship VARCHAR,
    date_of_birth          DATE,       -- source has "YYYY-MM-DD 00:00:00"
    position               VARCHAR,
    sub_position           VARCHAR,
    foot                   VARCHAR,
    height_in_cm           INTEGER
);

CREATE TABLE tm_player_valuations (
    player_id                           BIGINT NOT NULL,
    date                                DATE NOT NULL,
    market_value_in_eur                 BIGINT,
    current_club_id                     BIGINT,   -- club on the valuation row (not always reliable)
    current_club_name                   VARCHAR,
    player_club_domestic_competition_id VARCHAR
);

CREATE TABLE tm_clubs (
    club_id                 BIGINT NOT NULL,
    club_code               VARCHAR,
    name                    VARCHAR,
    domestic_competition_id VARCHAR
);

CREATE TABLE tm_appearances (
    appearance_id  VARCHAR NOT NULL,
    game_id        BIGINT NOT NULL,
    player_id      BIGINT NOT NULL,
    player_club_id BIGINT,
    date           DATE NOT NULL,
    player_name    VARCHAR,
    competition_id VARCHAR,
    minutes_played INTEGER,
    goals          INTEGER,
    assists        INTEGER,
    yellow_cards   INTEGER,
    red_cards      INTEGER
);
