"""Tests for the point-in-time event-sequence primitive (features/sequence)."""

from datetime import UTC, datetime, timedelta

from sentiment_signal.features.sequence import (
    SentimentEvent,
    events_asof,
    order_events,
)


def _ev(day: int, sid: str = "x", topic: int = 0) -> SentimentEvent:
    return SentimentEvent(
        statement_id=sid,
        timestamp=datetime(2020, 1, day, tzinfo=UTC),
        person="p",
        institution="i",
        influence_tier=1,
        source_type="speech",
        sentiment_score=0.0,
        hawkish_score=0.0,
        topic_main="Monetary policy",
        topic_id=topic,
    )


def test_order_events_sorts_ascending():
    events = [_ev(5), _ev(1), _ev(3)]
    ordered = order_events(events)
    assert [e.timestamp.day for e in ordered] == [1, 3, 5]


def test_asof_excludes_present_and_future_by_default():
    events = order_events([_ev(1), _ev(2), _ev(3), _ev(4)])
    sel = events_asof(events, datetime(2020, 1, 3, tzinfo=UTC))
    # strictly before day 3 -> days 1, 2 only (no look-ahead, excludes day 3 itself)
    assert [e.timestamp.day for e in sel] == [1, 2]


def test_asof_inclusive_admits_exact_time():
    events = order_events([_ev(1), _ev(2), _ev(3)])
    sel = events_asof(events, datetime(2020, 1, 3, tzinfo=UTC), inclusive=True)
    assert [e.timestamp.day for e in sel] == [1, 2, 3]


def test_asof_never_leaks_future():
    events = order_events([_ev(d) for d in range(1, 11)])
    t = datetime(2020, 1, 6, tzinfo=UTC)
    sel = events_asof(events, t)
    assert all(e.timestamp < t for e in sel)


def test_asof_lookback_window_bounds_history():
    events = order_events([_ev(d) for d in range(1, 11)])
    sel = events_asof(events, datetime(2020, 1, 9, tzinfo=UTC), lookback=timedelta(days=3))
    # window [day6, day9) -> days 6, 7, 8
    assert [e.timestamp.day for e in sel] == [6, 7, 8]


def test_asof_naive_timestamp_treated_as_utc():
    naive = SentimentEvent("x", datetime(2020, 1, 2), "p", "i", 1, "speech", 0.0, 0.0, "m", 0)
    sel = events_asof([naive], datetime(2020, 1, 3, tzinfo=UTC))
    assert len(sel) == 1
