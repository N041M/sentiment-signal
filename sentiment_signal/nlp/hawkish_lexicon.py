"""Rule-based hawkish/dovish scorer for central bank text.

Based on the monetary policy lexicon approach used in the FOMC NLP
literature (Apel & Blix Grimaldi 2012; Schmeling & Wagner 2019).

hawkish_score = (hawkish_hits - dovish_hits) / (total_hits + SMOOTHING)
  > 0 → hawkish (restrictive / inflation-fighting)
  < 0 → dovish  (accommodative / growth-supporting)
  = 0 → neutral or no signal

The SMOOTHING term is deliberate: a plain (hawk - dove)/total normalisation maps any
one-sided document to exactly ±1.0 — a single matched keyword scores the same as a
strongly one-sided speech. Additive (Laplace) smoothing pulls thin evidence toward
neutral, so the magnitude reflects evidence strength: 1 dovish hit → −0.33, 10 → −0.83.
"""

from __future__ import annotations

# Pseudo-counts of neutral evidence; regularises thin/one-sided matches toward 0.
SMOOTHING = 2

# Words/phrases strongly associated with tightening/restrictive stance
HAWKISH = frozenset(
    [
        "raise rates",
        "rate hike",
        "rate increase",
        "increase rates",
        "tighten",
        "tightening",
        "restrictive",
        "above neutral",
        "upside risk",
        "upside risks",
        "inflation risk",
        "inflation risks",
        "inflation expectations",
        "overheating",
        "overheat",
        "price stability",
        "price pressures",
        "inflationary",
        "hawkish",
        "less accommodative",
        "remove accommodation",
        "normalize",
        "normalisation",
        "normalization",
        "reduce balance sheet",
        "quantitative tightening",
        "qt",
        "above target",
        "persistent inflation",
        "wage growth",
        "labor market tight",
        "labour market tight",
        "above-target",
        "inflation above",
    ]
)

# Words/phrases strongly associated with easing/accommodative stance
DOVISH = frozenset(
    [
        "cut rates",
        "rate cut",
        "rate reduction",
        "lower rates",
        "ease",
        "easing",
        "accommodative",
        "below neutral",
        "downside risk",
        "downside risks",
        "recession risk",
        "unemployment",
        "labor market slack",
        "labour market slack",
        "below target",
        "inflation below",
        "deflationary",
        "dovish",
        "more accommodation",
        "additional support",
        "quantitative easing",
        "qe",
        "asset purchases",
        "forward guidance",
        "lower for longer",
        "support the economy",
        "economic support",
        "weak growth",
        "subdued inflation",
        "below-target",
    ]
)


def score(text: str) -> dict:
    """Return hawkish_score ∈ [-1, 1], label, and hit counts."""
    text_lower = text.lower()
    hawk_hits = sum(1 for term in HAWKISH if term in text_lower)
    dove_hits = sum(1 for term in DOVISH if term in text_lower)
    total = hawk_hits + dove_hits
    # Smoothed net tone in (-1, 1); never clamps to ±1 on thin one-sided evidence.
    raw_score = (hawk_hits - dove_hits) / (total + SMOOTHING)

    if total == 0:
        label = "neutral"
    elif raw_score > 0.1:
        label = "hawkish"
    elif raw_score < -0.1:
        label = "dovish"
    else:
        label = "neutral"

    return {
        "hawkish_score": float(raw_score),
        "hawkish_label": label,
        "hawk_hits": hawk_hits,
        "dove_hits": dove_hits,
    }


def score_batch(texts: list[str]) -> list[dict]:
    return [score(t) for t in texts]
