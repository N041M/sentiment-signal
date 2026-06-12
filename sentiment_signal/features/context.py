"""Macro-context overlay: which curated high-impact periods are active at a time.

A statement / market event / signal is "in" a context period when its timestamp
falls within [start_date, end_date); end_date None means ongoing. Periods overlap
(e.g. a pandemic and an easing cycle coincide), so a timestamp can map to several.

Intended use is analytical stratification — slice or condition results by regime.
If a regime label is ever used as a *model feature*, define it causally to avoid
look-ahead bias (the label at time T must use only information available at T).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sentiment_signal.db.models import ContextPeriod


def is_active(start: datetime, end: datetime | None, ts: datetime) -> bool:
    """True if `ts` falls in [start, end); end None = ongoing (open-ended)."""
    if ts < start:
        return False
    return end is None or ts < end


def active_contexts(ts: datetime, session: Session) -> list[ContextPeriod]:
    """All context periods active at `ts`, most systemic (lowest impact_tier) first."""
    return list(
        session.scalars(
            select(ContextPeriod)
            .where(
                ContextPeriod.start_date <= ts,
                or_(ContextPeriod.end_date.is_(None), ContextPeriod.end_date > ts),
            )
            .order_by(ContextPeriod.impact_tier.nullslast(), ContextPeriod.start_date)
        ).all()
    )


def contexts_overlapping(
    window_start: datetime, window_end: datetime, session: Session
) -> list[ContextPeriod]:
    """All context periods that overlap the closed window [window_start, window_end]."""
    return list(
        session.scalars(
            select(ContextPeriod)
            .where(
                ContextPeriod.start_date <= window_end,
                or_(ContextPeriod.end_date.is_(None), ContextPeriod.end_date >= window_start),
            )
            .order_by(ContextPeriod.start_date)
        ).all()
    )


def all_periods(session: Session) -> list[ContextPeriod]:
    """Every context period, ordered by start date (for catalog/timeline views)."""
    return list(session.scalars(select(ContextPeriod).order_by(ContextPeriod.start_date)).all())
