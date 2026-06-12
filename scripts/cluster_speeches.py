#!/usr/bin/env python3
"""Topic-model the speech corpus with BERTopic and write
cluster_id / topic_main / topic_classification / umap_x / umap_y.

Uses sentence-transformer (topic-semantic) embeddings + BERTopic, replacing the old
FinBERT-embedding HDBSCAN clustering that produced topic-incoherent blobs (build log
§13.25). cluster_id = BERTopic topic id; topic_classification = the topic's c-TF-IDF
words (data-driven sub-topic); topic_main = the lexicon's broad headline for those
words.

Usage (from project root, venv active):
    python scripts/cluster_speeches.py
    python scripts/cluster_speeches.py --min-topic-size 25 --embed-model all-mpnet-base-v2

First-time run on an existing database:
    psql $DATABASE_URL < db/migrations/001_add_clustering_columns.sql
    psql $DATABASE_URL < db/migrations/003_add_topic_main.sql
    python scripts/cluster_speeches.py
"""

import argparse
import sys

sys.path.insert(0, ".")

from loguru import logger
from sqlalchemy import select, text

from sentiment_signal.db.models import Statement, StatementAnalysis
from sentiment_signal.db.session import SessionLocal
from sentiment_signal.nlp.topic_model import DEFAULT_EMBED_MODEL, fit_topics


def _ensure_columns(session) -> None:
    """Add clustering columns if a migration has not been applied yet.

    Checks information_schema first and only ALTERs genuinely missing columns: a
    no-op ALTER still takes an ACCESS EXCLUSIVE lock, which queues behind — and
    then blocks — every concurrent reader (e.g. an open dashboard), hanging it.
    The short lock_timeout makes us fail fast rather than hang if a lock is held.
    """
    wanted = {
        "cluster_id": "INTEGER",
        "umap_x": "FLOAT",
        "umap_y": "FLOAT",
        "topic_main": "VARCHAR(80)",
    }
    existing = {
        r[0]
        for r in session.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_name='statement_analysis'"
            )
        )
    }
    missing = {c: d for c, d in wanted.items() if c not in existing}
    if not missing:
        return
    for col, dtype in missing.items():
        try:
            session.execute(text("SET lock_timeout = '5s'"))
            session.execute(
                text(f"ALTER TABLE statement_analysis ADD COLUMN IF NOT EXISTS {col} {dtype}")
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning(f"Column {col}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BERTopic topic modelling of speeches")
    parser.add_argument(
        "--min-topic-size", type=int, default=20, help="BERTopic min_topic_size (default 20)"
    )
    parser.add_argument(
        "--embed-model",
        default=DEFAULT_EMBED_MODEL,
        help=f"sentence-transformer model (default {DEFAULT_EMBED_MODEL})",
    )
    parser.add_argument(
        "--nr-topics",
        type=int,
        default=None,
        help="Optionally reduce to this many topics (default: natural count)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    _ensure_columns(session)

    logger.info("Loading speech texts from database…")
    rows = session.execute(
        select(StatementAnalysis.id, Statement.raw_text)
        .join(Statement, StatementAnalysis.statement_id == Statement.id)
        .where(StatementAnalysis.embedding.isnot(None))
        .order_by(StatementAnalysis.id)
    ).all()

    if len(rows) < 20:
        logger.error(f"Only {len(rows)} scored statements found — need >=20. Run step 3 first.")
        session.close()
        return

    analysis_ids = [r.id for r in rows]
    texts = [r.raw_text or "" for r in rows]

    result = fit_topics(
        texts,
        embed_model=args.embed_model,
        min_topic_size=args.min_topic_size,
        nr_topics=args.nr_topics,
    )

    n_topics = len([t for t in result.sizes if t != -1])
    logger.info(f"BERTopic produced {n_topics} topics")
    print("\nTopics (id | size | main headline | secondary c-TF-IDF):")
    print(f"  {'id':>4}  {'size':>5}  {'main':<26}  secondary")
    print("  " + "-" * 80)
    for tid, n in sorted(result.sizes.items(), key=lambda kv: -kv[1]):
        print(f"  {tid:>4}  {n:>5}  {result.main_of[tid]:<26}  {result.secondary_of[tid][:44]}")

    logger.info("Writing topic assignments to database…")
    for aid, tid, ux, uy in zip(analysis_ids, result.topic_ids, result.umap_x, result.umap_y):
        session.execute(
            text("""
                UPDATE statement_analysis
                   SET cluster_id           = :cid,
                       topic_main           = :main,
                       topic_classification = :secondary,
                       umap_x               = :ux,
                       umap_y               = :uy
                 WHERE id = :aid
            """),
            {
                "cid": tid,
                "main": result.main_of[tid],
                "secondary": result.secondary_of[tid],
                "ux": ux,
                "uy": uy,
                "aid": str(aid),
            },
        )
    session.commit()
    logger.info(f"Done — {len(analysis_ids)} rows updated")
    session.close()


if __name__ == "__main__":
    main()
