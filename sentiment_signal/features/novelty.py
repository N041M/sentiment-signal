"""Engineered novelty / habituation-pressure feature (architecture_v2 baseline).

For each statement, the recency-weighted count of recent prior statements on the SAME
topic (point-in-time) — i.e. how *familiar* the market already is with this theme. The
user's hypothesis is that market |response| falls as this pressure rises ("the market
is used to it"). Computed from the statement sequence alone (no market labels), so it
(a) directly tests the habituation hypothesis and (b) is the baseline a learned,
task-independent sentiment model must beat to justify its complexity.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sentiment_signal.features.sequence import SentimentEvent


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def recent_similar_pressure(
    events: Sequence[SentimentEvent],
    *,
    half_life_days: float = 14.0,
    lookback_days: float = 90.0,
) -> list[float]:
    """Per event (returned in input order), the recency-weighted count of prior
    SAME-topic events within `lookback_days`. Weight of a prior at lag Δdays is
    0.5 ** (Δ / half_life_days). Strictly point-in-time (only events before each one;
    ties at the same instant are excluded). Events with no topic_id get 0.
    """
    out = [0.0] * len(events)
    by_topic: dict[int | None, list[int]] = {}
    for i, e in enumerate(events):
        by_topic.setdefault(e.topic_id, []).append(i)

    for tid, idxs in by_topic.items():
        if tid is None:
            continue
        idxs_sorted = sorted(idxs, key=lambda i: _utc(events[i].timestamp))
        times = [_utc(events[i].timestamp) for i in idxs_sorted]
        for k, orig_i in enumerate(idxs_sorted):
            t = times[k]
            lo = t - timedelta(days=lookback_days)
            pressure = 0.0
            for j in range(k - 1, -1, -1):  # walk priors newest-first
                tj = times[j]
                if tj < lo:
                    break  # everything earlier is out of the window
                if tj >= t:
                    continue  # exclude same-instant ties (point-in-time)
                lag_days = (t - tj).total_seconds() / 86400.0
                pressure += 0.5 ** (lag_days / half_life_days)
            out[orig_i] = pressure
    return out
