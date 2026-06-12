-- Sentiment Signal — full database schema
-- PostgreSQL 16 + pgvector

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Persons ──────────────────────────────────────────────────────────────────

CREATE TABLE persons (
    id              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name  VARCHAR(255) NOT NULL UNIQUE,
    aliases         TEXT[]       NOT NULL DEFAULT '{}',
    role            VARCHAR(255),
    institution     VARCHAR(255),
    influence_tier  SMALLINT     NOT NULL CHECK (influence_tier BETWEEN 1 AND 4),
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── Scraper registry & audit ──────────────────────────────────────────────────

CREATE TABLE scrapers (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(100) NOT NULL UNIQUE,
    version      VARCHAR(20)  NOT NULL,
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT true,
    last_run_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE scraper_errors (
    id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    scraper_name   VARCHAR(100) NOT NULL,
    error_message  TEXT         NOT NULL,
    error_type     VARCHAR(100),
    stack_trace    TEXT,
    occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE collection_runs (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    scraper_name        VARCHAR(100) NOT NULL,
    started_at          TIMESTAMPTZ  NOT NULL,
    finished_at         TIMESTAMPTZ,
    items_collected     INTEGER      DEFAULT 0,
    items_deduplicated  INTEGER      DEFAULT 0,
    status              VARCHAR(20)  NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'success', 'error')),
    notes               TEXT
);

-- ── Channel 1A — Statements ───────────────────────────────────────────────────

CREATE TABLE statements (
    id                   UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id            UUID         NOT NULL REFERENCES persons(id),
    source_type          VARCHAR(50)  NOT NULL,
    raw_text             TEXT         NOT NULL,
    content_hash         CHAR(64)     NOT NULL UNIQUE,
    url                  VARCHAR(2048),
    published_at         TIMESTAMPTZ  NOT NULL,
    influence_tier       SMALLINT     NOT NULL,
    statement_subtype    VARCHAR(50),
    parent_statement_id  UUID         REFERENCES statements(id),
    is_processed         BOOLEAN      NOT NULL DEFAULT false,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_statements_person_id   ON statements(person_id);
CREATE INDEX idx_statements_published   ON statements(published_at DESC);
CREATE INDEX idx_statements_unprocessed ON statements(is_processed) WHERE is_processed = false;

-- ── Channel 1B — Reactions ────────────────────────────────────────────────────

CREATE TABLE reactions (
    id                       UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    statement_id             UUID        REFERENCES statements(id),
    link_confidence          SMALLINT    NOT NULL CHECK (link_confidence BETWEEN 1 AND 3),
    platform                 VARCHAR(50) NOT NULL,
    raw_text                 TEXT        NOT NULL,
    content_hash             CHAR(64)    NOT NULL UNIQUE,
    published_at             TIMESTAMPTZ NOT NULL,
    net_score                INTEGER     DEFAULT 0,
    engagement_score         FLOAT,
    content_depth            SMALLINT    NOT NULL DEFAULT 0
                                 CHECK (content_depth BETWEEN 0 AND 2),
    is_within_primary_window BOOLEAN     NOT NULL DEFAULT true,
    is_processed             BOOLEAN     NOT NULL DEFAULT false,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reactions_statement    ON reactions(statement_id);
CREATE INDEX idx_reactions_published    ON reactions(published_at DESC);
CREATE INDEX idx_reactions_unprocessed  ON reactions(is_processed) WHERE is_processed = false;

CREATE TABLE reaction_aggregates_raw (
    id                   UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    statement_id         UUID        NOT NULL UNIQUE REFERENCES statements(id),
    reaction_count       INTEGER     NOT NULL DEFAULT 0,
    mean_engagement_score FLOAT,
    total_net_score      INTEGER     DEFAULT 0,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Channel 2 — NLP analysis ──────────────────────────────────────────────────

CREATE TABLE statement_analysis (
    id                   UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    statement_id         UUID        NOT NULL UNIQUE REFERENCES statements(id),
    sentiment_score      FLOAT,
    sentiment_label      VARCHAR(10) CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
    emotion_vector       JSONB,
    topic_classification VARCHAR(120),
    topic_main           VARCHAR(80),
    entity_mentions      TEXT[],
    embedding            vector(768),
    finbert_score        FLOAT,
    hawkish_score        FLOAT,
    hawkish_label        VARCHAR(10),
    cluster_id           INTEGER,
    umap_x               FLOAT,
    umap_y               FLOAT,
    model_version        VARCHAR(50),
    scored_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_stmt_analysis_embedding
    ON statement_analysis USING hnsw (embedding vector_cosine_ops);

CREATE TABLE reaction_analysis (
    id                      UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    reaction_id             UUID        NOT NULL UNIQUE REFERENCES reactions(id),
    statement_id            UUID        NOT NULL REFERENCES statements(id),
    sentiment_score         FLOAT,
    agreement_score         FLOAT,
    emotion_vector          JSONB,
    engagement_weighted_score FLOAT,
    embedding               vector(768),
    model_version           VARCHAR(50),
    scored_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rxn_analysis_statement ON reaction_analysis(statement_id);
CREATE INDEX idx_rxn_analysis_embedding
    ON reaction_analysis USING hnsw (embedding vector_cosine_ops);

-- ── Aggregated sentiment signal ───────────────────────────────────────────────

CREATE TABLE sentiment_signal (
    id                       UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    statement_id             UUID        NOT NULL UNIQUE REFERENCES statements(id),
    person_id                UUID        NOT NULL REFERENCES persons(id),
    timestamp                TIMESTAMPTZ NOT NULL,
    statement_sentiment      FLOAT,
    mean_reaction_sentiment  FLOAT,
    reaction_variance        FLOAT,
    engagement_weighted_delta FLOAT,
    agreement_ratio          FLOAT,
    reaction_count           INTEGER     NOT NULL DEFAULT 0,
    time_to_peak_reaction    INTERVAL,
    sharpe_analog            FLOAT,
    hawkish_score            FLOAT,
    computed_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_signal_person    ON sentiment_signal(person_id);
CREATE INDEX idx_signal_timestamp ON sentiment_signal(timestamp DESC);

-- ── Channel 3 — Market data ───────────────────────────────────────────────────

CREATE TABLE price_data (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol      VARCHAR(20) NOT NULL,
    granularity VARCHAR(10) NOT NULL CHECK (granularity IN ('1d', '1h')),
    timestamp   TIMESTAMPTZ NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      BIGINT,
    UNIQUE (symbol, granularity, timestamp)
);

CREATE INDEX idx_price_symbol_ts ON price_data(symbol, timestamp DESC);

CREATE TABLE macro_data (
    id        UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    series_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    value     NUMERIC     NOT NULL,
    UNIQUE (series_id, timestamp)
);

CREATE INDEX idx_macro_series_ts ON macro_data(series_id, timestamp DESC);

-- ── Ground truth events ───────────────────────────────────────────────────────

CREATE TABLE events (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type    VARCHAR(50) NOT NULL,
    domain        VARCHAR(50) NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    window_hours  INTEGER     NOT NULL DEFAULT 24,
    magnitude_pct NUMERIC,
    magnitude_z   FLOAT,        -- move in per-market return std (volatility-normalised)
    direction     SMALLINT    CHECK (direction IN (-1, 0, 1)),
    threshold_pct NUMERIC,
    is_scheduled  BOOLEAN     NOT NULL DEFAULT false,
    source        VARCHAR(50) NOT NULL,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_events_unique ON events(domain, timestamp, event_type);
CREATE INDEX idx_events_domain_ts ON events(domain, timestamp DESC);
CREATE INDEX idx_events_type      ON events(event_type);

CREATE TABLE event_context (
    id                          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id                    UUID        NOT NULL REFERENCES events(id),
    statement_ids               UUID[],
    sentiment_signal_ids        UUID[],
    lookback_window_hours       INTEGER     NOT NULL DEFAULT 48,
    mean_signal_in_window       FLOAT,
    dominant_person             VARCHAR(255),
    model_prediction_direction  SMALLINT    CHECK (model_prediction_direction IN (-1, 0, 1)),
    model_prediction_magnitude  FLOAT,
    prediction_error            FLOAT,
    was_correct                 BOOLEAN,
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_event_context_event ON event_context(event_id);

-- ── Macro context overlay (curated high-impact events / regimes) ───────────────

CREATE TABLE context_periods (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(255) NOT NULL UNIQUE,
    category     VARCHAR(50)  NOT NULL,
    start_date   TIMESTAMPTZ  NOT NULL,
    end_date     TIMESTAMPTZ,                 -- NULL = ongoing
    onset_date   TIMESTAMPTZ,                 -- acute moment, if distinct from start
    impact_tier  SMALLINT     CHECK (impact_tier BETWEEN 1 AND 3),
    geography    VARCHAR(100),
    description  TEXT,
    source_url   VARCHAR(2048),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_context_periods_dates    ON context_periods(start_date, end_date);
CREATE INDEX idx_context_periods_category ON context_periods(category);
