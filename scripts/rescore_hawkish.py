#!/usr/bin/env python3
"""(Re)score central-bank speeches with hawkish/dovish stance.

Hawkish/dovish is a MONETARY-POLICY signal, so it is only applied to central-bank
speeches (source_type='speech'). Any hawkish score previously written to other
document types (executive orders, UN news, etc.) is nulled — applying a monetary
lexicon to a sanctions proclamation is a category error and produced a spurious
−1.0 cluster.

Uses FOMC-RoBERTa when available, otherwise the smoothed rule-based lexicon.
Re-scores all speeches each run so lexicon changes take effect.

Run from project root with venv active:
    python scripts/rescore_hawkish.py
"""

import sys

sys.path.insert(0, ".")

from collections import Counter

from loguru import logger
from sqlalchemy import select, update

from sentiment_signal.db.models import Statement, StatementAnalysis
from sentiment_signal.db.session import SessionLocal


def main() -> None:
    session = SessionLocal()
    try:
        # 1. Null hawkish scores wrongly applied to non-speech documents.
        cleared = session.execute(
            update(StatementAnalysis)
            .where(
                StatementAnalysis.statement_id.in_(
                    select(Statement.id).where(Statement.source_type != "speech")
                )
            )
            .values(hawkish_score=None, hawkish_label=None)
        ).rowcount
        session.commit()
        logger.info(f"Cleared hawkish scores on {cleared} non-speech statements")

        # 2. Score all central-bank speeches.
        speeches = session.execute(
            select(Statement.id, Statement.raw_text)
            .join(StatementAnalysis, StatementAnalysis.statement_id == Statement.id)
            .where(Statement.source_type == "speech")
        ).all()
        logger.info(f"Speeches to score: {len(speeches)}")
        if not speeches:
            return

        ids = [str(r.id) for r in speeches]
        texts = [r.raw_text for r in speeches]

        try:
            from sentiment_signal.nlp.pipeline import NLPPipeline

            logger.info(f"Scoring {len(texts)} speeches with FOMC-RoBERTa")
            results = NLPPipeline().score_hawkish_dovish(texts)
            method = "FOMC-RoBERTa"
        except Exception as exc:
            logger.warning(
                f"FOMC-RoBERTa unavailable ({exc.__class__.__name__}), "
                f"falling back to rule-based lexicon"
            )
            from sentiment_signal.nlp.hawkish_lexicon import score_batch

            results = score_batch(texts)
            method = "lexicon"

        for stmt_id, result in zip(ids, results):
            analysis = session.scalar(
                select(StatementAnalysis).where(StatementAnalysis.statement_id == stmt_id)
            )
            if analysis:
                analysis.hawkish_score = result["hawkish_score"]
                analysis.hawkish_label = result["hawkish_label"]
        session.commit()
        logger.info(f"Done — scored {len(results)} speeches via {method}")
        logger.info(f"Label distribution: {dict(Counter(r['hawkish_label'] for r in results))}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
