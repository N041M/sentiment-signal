"""Unit tests for the sharpe_analog feature — the thesis's primary novel signal.

These are pure-function tests (no database), so they run without PostgreSQL/pgvector.
"""

import math

import pytest

from sentiment_signal.features.signal import agreement_ratio, compute_sharpe_analog


class TestComputeSharpeAnalog:
    def test_returns_none_with_fewer_than_two_reactions(self):
        assert compute_sharpe_analog(0.5, [], []) is None
        assert compute_sharpe_analog(0.5, [0.3], [1.0]) is None

    def test_returns_none_when_reaction_variance_is_zero(self):
        # Identical reactions -> std == 0 -> undefined ratio
        assert compute_sharpe_analog(0.8, [0.2, 0.2, 0.2], [1.0, 1.0, 1.0]) is None

    def test_positive_when_statement_exceeds_reaction_mean(self):
        # Statement more positive than the crowd -> positive delta -> positive analog
        result = compute_sharpe_analog(0.9, [0.1, -0.1], [1.0, 1.0])
        assert result is not None
        assert result > 0

    def test_negative_when_statement_below_reaction_mean(self):
        result = compute_sharpe_analog(-0.5, [0.4, 0.6], [1.0, 1.0])
        assert result is not None
        assert result < 0

    def test_known_value(self):
        # statement=1.0, reactions=[0.0, 0.5], equal weights
        # weighted_mean = 0.25, delta = 0.75, std = 0.25 -> 3.0
        result = compute_sharpe_analog(1.0, [0.0, 0.5], [1.0, 1.0])
        assert result == pytest.approx(3.0)

    def test_engagement_weighting_shifts_mean(self):
        # Heavier weight on the more negative reaction pulls weighted_mean down,
        # increasing the delta vs an unweighted mean.
        weighted = compute_sharpe_analog(1.0, [0.0, 0.8], [9.0, 1.0])
        unweighted = compute_sharpe_analog(1.0, [0.0, 0.8], [1.0, 1.0])
        assert weighted > unweighted

    def test_zero_weights_fall_back_to_equal_weighting(self):
        # All-zero weights must not divide by zero; should equal equal-weight result
        zero_w = compute_sharpe_analog(1.0, [0.0, 0.5], [0.0, 0.0])
        equal_w = compute_sharpe_analog(1.0, [0.0, 0.5], [1.0, 1.0])
        assert zero_w == pytest.approx(equal_w)

    def test_result_is_finite(self):
        result = compute_sharpe_analog(0.3, [0.1, 0.2, -0.4, 0.5], [2.0, 1.0, 3.0, 1.0])
        assert result is not None and math.isfinite(result)


class TestAgreementRatio:
    def test_returns_none_with_no_reactions(self):
        assert agreement_ratio(0.5, []) is None

    def test_all_agree(self):
        # Statement positive, all reactions positive -> ratio 1.0
        assert agreement_ratio(0.5, [0.1, 0.9, 0.3]) == 1.0

    def test_all_disagree(self):
        assert agreement_ratio(0.5, [-0.1, -0.9, -0.3]) == 0.0

    def test_half_agree(self):
        assert agreement_ratio(0.5, [0.2, -0.2]) == pytest.approx(0.5)

    def test_zero_statement_treated_as_positive_sign(self):
        # stmt_sign for 0.0 is +1; reactions >= 0 match
        assert agreement_ratio(0.0, [0.0, 0.1]) == 1.0
