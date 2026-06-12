from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Interval,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from sentiment_signal.db.session import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String(255), nullable=False, unique=True)
    aliases = Column(ARRAY(Text), server_default="{}")
    role = Column(String(255))
    institution = Column(String(255))
    influence_tier = Column(SmallInteger, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    statements = relationship("Statement", back_populates="person")
    sentiment_signals = relationship("SentimentSignalRecord", back_populates="person")


class Scraper(Base):
    __tablename__ = "scrapers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    version = Column(String(20), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default="true")
    last_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class ScraperError(Base):
    __tablename__ = "scraper_errors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scraper_name = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    error_type = Column(String(100))
    stack_trace = Column(Text)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scraper_name = Column(String(100), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    items_collected = Column(Integer, server_default="0")
    items_deduplicated = Column(Integer, server_default="0")
    status = Column(String(20), nullable=False, server_default="running")
    notes = Column(Text)


class Statement(Base):
    __tablename__ = "statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False)
    source_type = Column(String(50), nullable=False)
    raw_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True)
    url = Column(String(2048))
    published_at = Column(DateTime(timezone=True), nullable=False)
    influence_tier = Column(SmallInteger, nullable=False)
    statement_subtype = Column(String(50))
    parent_statement_id = Column(UUID(as_uuid=True), ForeignKey("statements.id"))
    is_processed = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    person = relationship("Person", back_populates="statements")
    reactions = relationship("Reaction", back_populates="statement")
    analysis = relationship("StatementAnalysis", back_populates="statement", uselist=False)
    sentiment_signal = relationship(
        "SentimentSignalRecord", back_populates="statement", uselist=False
    )


class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(UUID(as_uuid=True), ForeignKey("statements.id"))
    link_confidence = Column(SmallInteger, nullable=False)
    platform = Column(String(50), nullable=False)
    raw_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True)
    published_at = Column(DateTime(timezone=True), nullable=False)
    net_score = Column(Integer, server_default="0")
    engagement_score = Column(Float)
    content_depth = Column(SmallInteger, nullable=False, server_default="0")
    is_within_primary_window = Column(Boolean, nullable=False, server_default="true")
    is_processed = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    statement = relationship("Statement", back_populates="reactions")
    analysis = relationship("ReactionAnalysis", back_populates="reaction", uselist=False)


class ReactionAggregateRaw(Base):
    __tablename__ = "reaction_aggregates_raw"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False, unique=True
    )
    reaction_count = Column(Integer, nullable=False, server_default="0")
    mean_engagement_score = Column(Float)
    total_net_score = Column(Integer, server_default="0")
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class StatementAnalysis(Base):
    __tablename__ = "statement_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False, unique=True
    )
    sentiment_score = Column(Float)
    sentiment_label = Column(String(10))
    emotion_vector = Column(JSONB)
    topic_classification = Column(String(120))  # secondary context (BERTopic c-TF-IDF words)
    topic_main = Column(String(80))  # main headline (broad theme from topic_lexicon)
    entity_mentions = Column(ARRAY(Text))
    embedding = Column(Vector(768))
    finbert_score = Column(Float)
    hawkish_score = Column(Float)
    hawkish_label = Column(String(10))
    cluster_id = Column(Integer)
    umap_x = Column(Float)
    umap_y = Column(Float)
    model_version = Column(String(50))
    scored_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    statement = relationship("Statement", back_populates="analysis")


class ReactionAnalysis(Base):
    __tablename__ = "reaction_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reaction_id = Column(
        UUID(as_uuid=True), ForeignKey("reactions.id"), nullable=False, unique=True
    )
    statement_id = Column(UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False)
    sentiment_score = Column(Float)
    agreement_score = Column(Float)
    emotion_vector = Column(JSONB)
    engagement_weighted_score = Column(Float)
    embedding = Column(Vector(768))
    model_version = Column(String(50))
    scored_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    reaction = relationship("Reaction", back_populates="analysis")


class SentimentSignalRecord(Base):
    __tablename__ = "sentiment_signal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id = Column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=False, unique=True
    )
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    statement_sentiment = Column(Float)
    mean_reaction_sentiment = Column(Float)
    reaction_variance = Column(Float)
    engagement_weighted_delta = Column(Float)
    agreement_ratio = Column(Float)
    reaction_count = Column(Integer, nullable=False, server_default="0")
    time_to_peak_reaction = Column(Interval)
    sharpe_analog = Column(Float)
    hawkish_score = Column(Float)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    statement = relationship("Statement", back_populates="sentiment_signal")
    person = relationship("Person", back_populates="sentiment_signals")


class PriceData(Base):
    __tablename__ = "price_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False)
    granularity = Column(String(10), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    open = Column(Numeric)
    high = Column(Numeric)
    low = Column(Numeric)
    close = Column(Numeric)
    volume = Column(BigInteger)  # index volumes exceed int32; schema is BIGINT

    __table_args__ = (UniqueConstraint("symbol", "granularity", "timestamp"),)


class MacroData(Base):
    __tablename__ = "macro_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    value = Column(Numeric, nullable=False)

    __table_args__ = (UniqueConstraint("series_id", "timestamp"),)


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False)
    domain = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    window_hours = Column(Integer, nullable=False, server_default="24")
    magnitude_pct = Column(Numeric)  # raw % move
    magnitude_z = Column(Float)  # move in per-market return std (volatility-normalised)
    direction = Column(SmallInteger)
    threshold_pct = Column(Numeric)
    is_scheduled = Column(Boolean, nullable=False, server_default="false")
    source = Column(String(50), nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    contexts = relationship("EventContext", back_populates="event")


class EventContext(Base):
    __tablename__ = "event_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    statement_ids = Column(ARRAY(UUID(as_uuid=True)))
    sentiment_signal_ids = Column(ARRAY(UUID(as_uuid=True)))
    lookback_window_hours = Column(Integer, nullable=False, server_default="48")
    mean_signal_in_window = Column(Float)
    dominant_person = Column(String(255))
    model_prediction_direction = Column(SmallInteger)
    model_prediction_magnitude = Column(Float)
    prediction_error = Column(Float)
    was_correct = Column(Boolean)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    event = relationship("Event", back_populates="contexts")


class ContextPeriod(Base):
    """Curated high-impact real-world event/regime with a time window.

    A macro-context overlay (wars, pandemics, policy regimes) distinct from the
    programmatic price-move `events`. A statement/event/signal is "in" a period when
    its timestamp falls within [start_date, end_date); end_date NULL means ongoing.
    Periods may overlap (e.g. a pandemic and an easing cycle coincide).
    """

    __tablename__ = "context_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    category = Column(String(50), nullable=False)  # pandemic | war_conflict | monetary_policy | ...
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True))  # NULL = ongoing
    onset_date = Column(DateTime(timezone=True))  # acute moment, if distinct from start
    impact_tier = Column(SmallInteger)  # 1 global-systemic ... 3 notable
    geography = Column(String(100))
    description = Column(Text)
    source_url = Column(String(2048))  # citation for the dates
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
