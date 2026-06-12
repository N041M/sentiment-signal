"""Unit tests for the hawkish/dovish lexicon scorer.

Regression coverage for the spurious −1.0 cluster: a one-sided document must NOT
clamp to exactly ±1.0 (additive smoothing pulls thin evidence toward neutral).
"""

import pytest

from sentiment_signal.nlp.hawkish_lexicon import SMOOTHING, score


class TestHawkishLexicon:
    def test_no_keywords_is_neutral_zero(self):
        r = score("The meeting covered procedural and administrative matters.")
        assert r["hawkish_score"] == 0.0
        assert r["hawkish_label"] == "neutral"

    def test_single_dovish_term_is_mild_not_minus_one(self):
        # The bug: one dovish term used to score exactly -1.0
        r = score("We discussed a rate cut.")
        assert r["hawkish_score"] == pytest.approx(-1 / (1 + SMOOTHING))  # -0.333
        assert r["hawkish_score"] > -1.0
        assert r["hawkish_label"] == "dovish"

    def test_single_hawkish_term_is_mild_not_plus_one(self):
        r = score("We may consider a rate hike.")
        assert r["hawkish_score"] == pytest.approx(1 / (1 + SMOOTHING))  # +0.333
        assert r["hawkish_score"] < 1.0
        assert r["hawkish_label"] == "hawkish"

    def test_one_sided_document_never_reaches_extremes(self):
        # Even a heavily one-sided document stays strictly inside (-1, 1)
        heavy = "rate hike rate increase tighten restrictive hawkish overheating"
        r = score(heavy)
        assert 0 < r["hawkish_score"] < 1.0

    def test_more_evidence_gives_stronger_score(self):
        weak = score("We discussed a rate cut.")["hawkish_score"]
        strong = score("rate cut lower rates accommodative recession risk")["hawkish_score"]
        assert strong < weak < 0  # more dovish hits -> more negative

    def test_balanced_is_neutral(self):
        r = score("They weighed a rate hike against a rate cut.")
        assert r["hawkish_score"] == pytest.approx(0.0)
        assert r["hawkish_label"] == "neutral"
