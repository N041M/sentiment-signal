"""Tests for the macro-context overlay.

`is_active` is a pure function (no DB). `active_contexts` is exercised against the
Postgres test database and skips automatically if it is unavailable (conftest).
"""

from datetime import UTC, datetime

from sentiment_signal.db.models import ContextPeriod
from sentiment_signal.features.context import active_contexts, is_active


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


class TestIsActive:
    def test_inside_window(self):
        assert is_active(_dt(2020, 1, 1), _dt(2020, 12, 31), _dt(2020, 6, 1)) is True

    def test_before_start(self):
        assert is_active(_dt(2020, 1, 1), _dt(2020, 12, 31), _dt(2019, 6, 1)) is False

    def test_after_end_is_exclusive(self):
        # end is exclusive: a ts exactly at end is not active
        assert is_active(_dt(2020, 1, 1), _dt(2020, 12, 31), _dt(2020, 12, 31)) is False
        assert is_active(_dt(2020, 1, 1), _dt(2020, 12, 31), _dt(2021, 1, 1)) is False

    def test_at_start_is_inclusive(self):
        assert is_active(_dt(2020, 1, 1), _dt(2020, 12, 31), _dt(2020, 1, 1)) is True

    def test_ongoing_open_ended(self):
        # end None = ongoing → active for any ts at/after start
        assert is_active(_dt(2022, 2, 24), None, _dt(2030, 1, 1)) is True
        assert is_active(_dt(2022, 2, 24), None, _dt(2021, 1, 1)) is False


class TestActiveContexts:
    def test_overlapping_and_ongoing(self, db_session):
        db_session.add_all(
            [
                ContextPeriod(
                    name="Pandemic",
                    category="pandemic",
                    start_date=_dt(2020, 1, 1),
                    end_date=_dt(2023, 5, 1),
                    impact_tier=1,
                ),
                ContextPeriod(
                    name="Easing cycle",
                    category="monetary_policy",
                    start_date=_dt(2020, 3, 1),
                    end_date=_dt(2022, 3, 1),
                    impact_tier=2,
                ),
                ContextPeriod(
                    name="Ongoing war",
                    category="war_conflict",
                    start_date=_dt(2022, 2, 24),
                    end_date=None,
                    impact_tier=1,
                ),
                ContextPeriod(
                    name="Old regime",
                    category="monetary_policy",
                    start_date=_dt(2015, 1, 1),
                    end_date=_dt(2016, 1, 1),
                    impact_tier=3,
                ),
            ]
        )
        db_session.flush()

        # Mid-2020: pandemic + easing overlap; war/old not active
        names = {c.name for c in active_contexts(_dt(2020, 6, 1), db_session)}
        assert names == {"Pandemic", "Easing cycle"}

        # 2025: only the ongoing war is active
        names_2025 = {c.name for c in active_contexts(_dt(2025, 1, 1), db_session)}
        assert names_2025 == {"Ongoing war"}

    def test_ordering_systemic_first(self, db_session):
        db_session.add_all(
            [
                ContextPeriod(
                    name="Notable",
                    category="political",
                    start_date=_dt(2020, 1, 1),
                    end_date=None,
                    impact_tier=3,
                ),
                ContextPeriod(
                    name="Systemic",
                    category="pandemic",
                    start_date=_dt(2020, 1, 1),
                    end_date=None,
                    impact_tier=1,
                ),
            ]
        )
        db_session.flush()
        ordered = [c.name for c in active_contexts(_dt(2021, 1, 1), db_session)]
        assert ordered == ["Systemic", "Notable"]  # lowest impact_tier first
