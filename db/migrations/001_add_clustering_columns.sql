-- Migration 001: add UMAP + cluster columns to statement_analysis
-- Run once against an existing database:
--   psql $DATABASE_URL < db/migrations/001_add_clustering_columns.sql

ALTER TABLE statement_analysis
    ADD COLUMN IF NOT EXISTS cluster_id  INTEGER,
    ADD COLUMN IF NOT EXISTS umap_x      FLOAT,
    ADD COLUMN IF NOT EXISTS umap_y      FLOAT;
