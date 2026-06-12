"""Tests for the recency-weighted habituation-pressure feature (features/novelty)."""

from datetime import UTC, datetime

from sentiment_signal.features.novelty import recent_similar_pressure
from sentiment_signal.features.sequence import SentimentEvent


def _ev(day: int, topic: int) -> SentimentEvent:
    return SentimentEvent(
        statement_id=f"s{day}",
        timestamp=datetime(2020, 1, day, tzinfo=UTC),
        person="p",
        institution="i",
        influence_tier=1,
        source_type="speech",
        sentiment_score=0.0,
        hawkish_score=0.0,
        topic_main="m",
        topic_id=topic,
    )


def test_first_same_topic_event_has_zero_pressure():
    events = [_ev(1, 0), _ev(2, 0), _ev(3, 0)]
    p = recent_similar_pressure(events, half_life_days=14, lookback_days=90)
    assert p[0] == 0.0
    assert p[1] > 0 and p[2] > p[1]  # pressure accumulates with more recent priors


def test_different_topics_do_not_contribute():
    events = [_ev(1, 0), _ev(2, 1), _ev(3, 0)]
    p = recent_similar_pressure(events, half_life_days=14, lookback_days=90)
    assert p[1] == 0.0  # topic 1 has no prior topic-1 event
    # event[2] (topic 0) sees only event[0] (topic 0), not event[1] (topic 1)
    assert 0 < p[2] <= 1.0


def test_lookback_excludes_old_priors():
    old = SentimentEvent(
        "a", datetime(2020, 1, 1, tzinfo=UTC), "p", "i", 1, "speech", 0.0, 0.0, "m", 0
    )
    new = SentimentEvent(
        "b", datetime(2020, 2, 9, tzinfo=UTC), "p", "i", 1, "speech", 0.0, 0.0, "m", 0
    )  # 39 days later
    p = recent_similar_pressure([old, new], half_life_days=14, lookback_days=10)
    assert p[1] == 0.0  # prior is outside the 10-day window


def test_closer_prior_weighs_more_than_farther():
    near = recent_similar_pressure([_ev(1, 0), _ev(2, 0)], half_life_days=14)[1]
    far = recent_similar_pressure([_ev(1, 0), _ev(20, 0)], half_life_days=14)[1]
    assert near > far


def test_half_life_decay_value():
    # a single prior exactly one half-life (14 days) earlier weighs 0.5
    p = recent_similar_pressure([_ev(1, 0), _ev(15, 0)], half_life_days=14)
    assert abs(p[1] - 0.5) < 1e-9


def test_none_topic_gets_zero():
    events = [
        _ev(1, 0),
        SentimentEvent(
            "x", datetime(2020, 1, 2, tzinfo=UTC), "p", "i", 1, "speech", 0.0, 0.0, "m", None
        ),
    ]
    p = recent_similar_pressure(events)
    assert p[1] == 0.0
