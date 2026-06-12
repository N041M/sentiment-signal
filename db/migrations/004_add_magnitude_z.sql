-- Migration 004: volatility-normalised event magnitude.
-- magnitude_z is the move expressed in standard deviations of that market's own
-- daily-return distribution (pct_change / per-market std), so event size is
-- comparable across markets of different volatility (a 1% move in a calm index
-- is a larger event than 1% in a volatile one). magnitude_pct stays for raw %.
--   psql $DATABASE_URL < db/migrations/004_add_magnitude_z.sql

ALTER TABLE events ADD COLUMN IF NOT EXISTS magnitude_z FLOAT;
