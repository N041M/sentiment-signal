-- Migration 005: widen topic_classification for BERTopic c-TF-IDF secondary labels.
-- BERTopic secondaries are 3-4 comma-joined terms (e.g.
-- "emergency, national emergency, executive order, national") that exceed the
-- original VARCHAR(50) sized for the old single-word/short lexicon labels.
--   psql $DATABASE_URL < db/migrations/005_widen_topic_classification.sql

ALTER TABLE statement_analysis ALTER COLUMN topic_classification TYPE VARCHAR(120);
