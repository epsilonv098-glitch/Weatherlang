-- Cebu Pulse: silver layer and run log. Safe to re-run (IF NOT EXISTS).
-- All timestamps are TIMESTAMPTZ, i.e. stored as UTC instants; the gold views
-- and the website convert to Asia/Manila for display.

CREATE TABLE IF NOT EXISTS locations (
    id        SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    area_type TEXT NOT NULL CHECK (area_type IN ('metro', 'mainland', 'tourist')),
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL
);

-- One row per location per hour: weather + air quality. Holds recent past AND
-- forecast hours; gold views separate them with observed_at <= now().
CREATE TABLE IF NOT EXISTS observations_silver (
    location_id         SMALLINT NOT NULL REFERENCES locations (id),
    observed_at         TIMESTAMPTZ NOT NULL,
    temperature_c       DOUBLE PRECISION,
    apparent_temp_c     DOUBLE PRECISION,
    humidity_pct        DOUBLE PRECISION,
    wind_speed_kmh      DOUBLE PRECISION,
    wind_gust_kmh       DOUBLE PRECISION,
    precipitation_mm    DOUBLE PRECISION,
    weather_code        SMALLINT,
    pm2_5               DOUBLE PRECISION,
    pm10                DOUBLE PRECISION,
    us_aqi              SMALLINT,
    heat_index_category TEXT CHECK (heat_index_category IN ('Normal', 'Caution', 'Danger')),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The upsert target: one row per location and hour.
    PRIMARY KEY (location_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations_silver (observed_at);

-- Sea conditions for coastal (tourist) locations only.
CREATE TABLE IF NOT EXISTS marine_silver (
    location_id   SMALLINT NOT NULL REFERENCES locations (id),
    observed_at   TIMESTAMPTZ NOT NULL,
    wave_height_m DOUBLE PRECISION,
    wave_period_s DOUBLE PRECISION,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_marine_observed_at ON marine_silver (observed_at);

-- One row per pipeline execution, written at start and updated at the end.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    rows_ingested INTEGER NOT NULL DEFAULT 0,
    rows_rejected INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs (started_at DESC);
