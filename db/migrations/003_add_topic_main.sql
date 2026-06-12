-- Migration 003: main topic headline for clusters (two-level labelling).
-- topic_classification holds the secondary context; topic_main the broad headline.
--   psql $DATABASE_URL < db/migrations/003_add_topic_main.sql

ALTER TABLE statement_analysis
    ADD COLUMN IF NOT EXISTS topic_main VARCHAR(80);
