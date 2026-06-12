#!/usr/bin/env python3
"""Prototype diagnostic: does a multi-model sentiment PANEL carry complementary signal,
or do the models mostly agree (making a panel pointless)?

Runs three lenses on a stratified sample of statements and reduces each to one
comparable scalar in [-1, 1]:
  - general/social : cardiffnlp/twitter-roberta-base-sentiment-latest  -> P(pos) - P(neg)
  - financial      : ProsusAI/finbert                                   -> P(pos) - P(neg)
  - emotion        : j-hartmann/emotion-english-distilroberta-base      -> P(joy) - P(neg-emotions)

Reports: correlation matrix (Pearson + Spearman), sign-disagreement %, per-domain
general<->financial correlation (the routing-justification metric), and max-divergence
examples. Report-only — no DB writes, not wired into the pipeline. First-512-token
truncation (a divergence diagnostic, not production scoring). Run:
    python scripts/prototype_sentiment_panel.py
"""

import sys

sys.path.insert(0, ".")

import pandas as pd
import torch
from loguru import logger
from sqlalchemy import select
from transformers import pipeline

from sentiment_signal.db.models import Statement, StatementAnalysis
from sentiment_signal.db.session import SessionLocal

PER_TOPIC = 30  # stratified sample size per topic_main
MAX_CHARS = 3000  # ~512 tokens; trim before the tokenizer for speed
MODELS = {
    "general": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "financial": "ProsusAI/finbert",
    "emotion": "j-hartmann/emotion-english-distilroberta-base",
}


def _device():
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return -1


def _as_dict(scores: list[dict]) -> dict[str, float]:
    return {d["label"].lower(): d["score"] for d in scores}


def _polarity(scores: list[dict]) -> float:
    d = _as_dict(scores)
    if "positive" in d or "negative" in d:
        return d.get("positive", 0.0) - d.get("negative", 0.0)
    # cardiff fallback label order: LABEL_0=neg, LABEL_1=neu, LABEL_2=pos
    return d.get("label_2", 0.0) - d.get("label_0", 0.0)


def _emotion_valence(scores: list[dict]) -> float:
    d = _as_dict(scores)
    neg = d.get("anger", 0) + d.get("disgust", 0) + d.get("fear", 0) + d.get("sadness", 0)
    return d.get("joy", 0.0) - neg


def _emotion_top(scores: list[dict]) -> str:
    return max(scores, key=lambda x: x["score"])["label"]


def main() -> None:
    session = SessionLocal()
    rows = session.execute(
        select(StatementAnalysis.statement_id, Statement.raw_text, StatementAnalysis.topic_main)
        .join(Statement, Statement.id == StatementAnalysis.statement_id)
        .where(StatementAnalysis.topic_main.isnot(None))
    ).all()
    session.close()

    df = pd.DataFrame(rows, columns=["id", "text", "topic"])
    df = df[df["text"].str.len() > 200]
    sample = pd.concat(
        [g.sample(min(len(g), PER_TOPIC), random_state=42) for _, g in df.groupby("topic")]
    ).reset_index(drop=True)
    texts = [t[:MAX_CHARS] for t in sample["text"]]
    logger.info(f"Sampled {len(sample)} statements across {sample['topic'].nunique()} topics")

    device = _device()
    out = {}
    for key, model in MODELS.items():
        logger.info(f"Scoring with {key} ({model})…")
        pipe = pipeline(
            "text-classification",
            model=model,
            top_k=None,
            device=device,
            truncation=True,
            max_length=512,
        )
        out[key] = pipe(texts, batch_size=16)

    sample["general_pol"] = [_polarity(s) for s in out["general"]]
    sample["financial_pol"] = [_polarity(s) for s in out["financial"]]
    sample["emotion_val"] = [_emotion_valence(s) for s in out["emotion"]]
    sample["emotion_top"] = [_emotion_top(s) for s in out["emotion"]]

    dims = ["general_pol", "financial_pol", "emotion_val"]
    print("\n=== Pearson correlation (low/moderate = complementary) ===")
    print(sample[dims].corr(method="pearson").round(3).to_string())
    print("\n=== Spearman correlation ===")
    print(sample[dims].corr(method="spearman").round(3).to_string())

    nz = sample[(sample["general_pol"] != 0) & (sample["financial_pol"] != 0)]
    disagree = ((nz["general_pol"] > 0) != (nz["financial_pol"] > 0)).mean()
    print(f"\nGeneral vs financial sign-disagreement: {disagree:.1%} of {len(nz)} statements")

    print("\n=== per-domain general<->financial Pearson (routing justification) ===")
    for topic, g in sample.groupby("topic"):
        if len(g) >= 8 and g["general_pol"].std() > 0 and g["financial_pol"].std() > 0:
            r = g["general_pol"].corr(g["financial_pol"])
            print(f"  {topic:<26} n={len(g):3d}  r={r:+.3f}")

    sample["divergence"] = (sample["general_pol"] - sample["financial_pol"]).abs()
    print("\n=== top max-divergence statements (general vs financial) ===")
    top = sample.sort_values("divergence", ascending=False).head(8)
    for _, r in top.iterrows():
        print(
            f"  [{r['topic'][:18]:<18}] gen={r['general_pol']:+.2f} fin={r['financial_pol']:+.2f} "
            f"emo={r['emotion_val']:+.2f}({r['emotion_top']}) | {r['text'][:80].strip()}…"
        )

    mean_abs = sample[dims].corr().abs().where(lambda x: x < 1).stack().mean()
    print(
        f"\nVERDICT: mean |off-diagonal correlation| = {mean_abs:.3f} "
        f"({'complementary — panel adds signal' if mean_abs < 0.6 else 'largely redundant'})"
    )


if __name__ == "__main__":
    main()
