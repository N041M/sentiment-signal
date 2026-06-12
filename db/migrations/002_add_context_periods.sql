-- Migration 002: macro context overlay (curated high-impact events / regimes).
-- Run once against an existing database:
--   psql $DATABASE_URL < db/migrations/002_add_context_periods.sql
-- Then seed:
--   python scripts/seed_context_periods.py

CREATE TABLE IF NOT EXISTS context_periods (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(255) NOT NULL UNIQUE,
    category     VARCHAR(50)  NOT NULL,
    start_date   TIMESTAMPTZ  NOT NULL,
    end_date     TIMESTAMPTZ,
    onset_date   TIMESTAMPTZ,
    impact_tier  SMALLINT     CHECK (impact_tier BETWEEN 1 AND 3),
    geography    VARCHAR(100),
    description  TEXT,
    source_url   VARCHAR(2048),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_context_periods_dates    ON context_periods(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_context_periods_category ON context_periods(category);
