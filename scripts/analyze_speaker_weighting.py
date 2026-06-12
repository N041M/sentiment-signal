#!/usr/bin/env python3
"""Pre-Phase-2 viability test for speaker-authority weighting.

Tests the hypothesis behind "weigh people differently": if a statement's market
impact depends on *who* spoke, then restricting the sentiment -> return correlation
to higher-authority speakers (influence_tier, central bankers) should strengthen it.

This is the cheap *linear/stratified* proxy for the eventual *learned* weighting.
A null here does not rule out a learned model finding conditional interactions, but
a positive here would be strong motivation to build one. Re-run in Phase 2 once
reaction data exists and `mean_signal_in_window` reflects sharpe_analog, not raw
sentiment.

    python scripts/analyze_speaker_weighting.py
"""

import sys

sys.path.insert(0, ".")

import pandas as pd
from loguru import logger
from scipy.stats import pearsonr
from sqlalchemy import text

from sentiment_signal.db.session import SessionLocal

# Institutions whose head is a monetary-policy authority (relevance proxy).
CENTRAL_BANK_KEYS = (
    "federal reserve",
    "central bank",
    "european central",
    "bank of england",
    "bank of japan",
    "reserve bank",
    "bundesbank",
    "banque de",
    "monetary authority",
)
EQUITY_INDICES = ("^GSPC", "^IXIC", "^DJI", "^GDAXI", "^FTSE", "^N225")


def _corr(d: pd.DataFrame, col: str) -> str:
    d = d.dropna(subset=["sig", col])
    if len(d) < 8 or d["sig"].std() == 0 or d[col].std() == 0:
        return f"n={len(d):5d}   (too few / no variance)"
    r, p = pearsonr(d["sig"], d[col])
    return f"n={len(d):5d}   r={r:+.4f}  p={p:.4f}" + ("  <-- p<.05" if p < 0.05 else "")


def main() -> None:
    logger.info("Loading event_context joined to events + dominant speaker…")
    session = SessionLocal()
    df = pd.DataFrame(
        session.execute(
            text("""
            select ec.mean_signal_in_window as sig, e.magnitude_pct as mag,
                   e.magnitude_z as magz, e.direction as dir, e.domain as sym,
                   p.influence_tier as tier, p.institution as inst
            from event_context ec
            join events e  on e.id = ec.event_id
            join persons p on p.canonical_name = ec.dominant_person
            where ec.mean_signal_in_window is not null and e.magnitude_pct is not null
        """)
        ).all(),
        columns=["sig", "mag", "magz", "dir", "sym", "tier", "inst"],
    )
    session.close()

    df = df.astype({"sig": float, "mag": float, "magz": float, "dir": float, "tier": int})
    signed = df["mag"].min() < 0
    df["ret"] = df["mag"] if signed else df["mag"] * df["dir"]
    df["retz"] = df["magz"] if signed else df["magz"] * df["dir"]  # volatility-normalised return
    df["is_cb"] = (
        df["inst"].fillna("").str.lower().apply(lambda x: any(k in x for k in CENTRAL_BANK_KEYS))
    )
    logger.info(f"N={len(df)} pairs; magnitude_pct signed={signed}")

    def block(d: pd.DataFrame, target: str) -> None:
        print(f"  ALL                {_corr(d, target)}")
        for t in sorted(d["tier"].unique()):
            print(f"  tier {t}             {_corr(d[d.tier == t], target)}")
        print(f"  central bankers    {_corr(d[d.is_cb], target)}")
        print(f"  non-central-bank   {_corr(d[~d.is_cb], target)}")

    print("\n=== directional, RAW % return: corr(mean_signal, signed return) ===")
    block(df, "ret")
    print(
        "\n=== directional, VOLATILITY-NORMALISED (z) return: corr(mean_signal, signed z-return) ==="
    )
    block(df, "retz")

    cb_eq = df[df.is_cb & df.sym.isin(EQUITY_INDICES)]
    print(f"\n  central bankers x equity-index (normalised)   {_corr(cb_eq, 'retz')}")

    hc = df[df["magz"].abs() >= 2.0]
    print(f"\n=== high-conviction moves only (|z| >= 2, n={len(hc)}), normalised return ===")
    block(hc, "retz")


if __name__ == "__main__":
    main()
