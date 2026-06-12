from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentiment_signal.db.models import (
    ReactionAnalysis,
    SentimentSignalRecord,
    Statement,
    StatementAnalysis,
)


def compute_sharpe_analog(
    statement_sentiment: float,
    reaction_sentiments: list[float],
    engagement_scores: list[float],
) -> float | None:
    """engagement_weighted_delta / reaction_std_dev.

    Returns None when fewer than 2 reactions exist or variance is zero —
    both indicate insufficient signal to compute a meaningful ratio.
    """
    if len(reaction_sentiments) < 2:
        return None
    weights = np.array(engagement_scores, dtype=float)
    sentiments = np.array(reaction_sentiments, dtype=float)
    if weights.sum() == 0:
        weights = np.ones_like(weights)
    weighted_mean = float(np.average(sentiments, weights=weights))
    delta = statement_sentiment - weighted_mean
    std = float(np.std(sentiments))
    # Use an epsilon rather than == 0: floating-point std of near-identical
    # reactions (e.g. [0.2, 0.2, 0.2]) is a tiny non-zero like 2.7e-17, which
    # would otherwise produce an absurd ratio (~1e16) instead of None.
    if std < 1e-9:
        return None
    return delta / std


def agreement_ratio(
    statement_sentiment: float,
    reaction_sentiments: list[float],
) -> float | None:
    """Fraction of reactions whose polarity sign matches the statement."""
    if not reaction_sentiments:
        return None
    stmt_sign = 1 if statement_sentiment >= 0 else -1
    matches = sum(1 for r in reaction_sentiments if (1 if r >= 0 else -1) == stmt_sign)
    return matches / len(reaction_sentiments)


def build_signal_for_statement(statement_id: str, session: Session) -> SentimentSignalRecord | None:
    """Compute and upsert the sentiment_signal row for a processed statement."""
    stmt_analysis = session.scalar(
        select(StatementAnalysis).where(StatementAnalysis.statement_id == statement_id)
    )
    if stmt_analysis is None or stmt_analysis.sentiment_score is None:
        return None

    rxn_rows = session.scalars(
        select(ReactionAnalysis).where(ReactionAnalysis.statement_id == statement_id)
    ).all()

    sentiments = [r.sentiment_score for r in rxn_rows if r.sentiment_score is not None]
    engagements = [
        r.engagement_weighted_score or 0.0 for r in rxn_rows if r.sentiment_score is not None
    ]

    stmt = session.get(Statement, statement_id)
    if stmt is None:
        return None

    sharpe = compute_sharpe_analog(stmt_analysis.sentiment_score, sentiments, engagements)
    ratio = agreement_ratio(stmt_analysis.sentiment_score, sentiments)
    eng_mean = (
        float(np.average(sentiments, weights=engagements))
        if sentiments and sum(engagements) > 0
        else (float(np.mean(sentiments)) if sentiments else None)
    )
    eng_delta = (stmt_analysis.sentiment_score - eng_mean) if eng_mean is not None else None

    existing = session.scalar(
        select(SentimentSignalRecord).where(SentimentSignalRecord.statement_id == statement_id)
    )
    if existing is None:
        existing = SentimentSignalRecord(
            statement_id=statement_id,
            person_id=stmt.person_id,
            timestamp=stmt.published_at,
        )
        session.add(existing)

    existing.statement_sentiment = stmt_analysis.sentiment_score
    existing.mean_reaction_sentiment = float(np.mean(sentiments)) if sentiments else None
    existing.reaction_variance = float(np.std(sentiments)) if sentiments else None
    existing.engagement_weighted_delta = eng_delta
    existing.agreement_ratio = ratio
    existing.reaction_count = len(sentiments)
    existing.sharpe_analog = sharpe
    existing.computed_at = datetime.now(UTC)
    session.commit()
    return existing
