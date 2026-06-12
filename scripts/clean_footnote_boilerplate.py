#!/usr/bin/env python3
"""Backfill: strip Fed footnote/nav boilerplate from already-stored statement text.

The Fed speech HTML embeds "Return to text" back-links and "(PDF)"/"(HTML)" link
labels inside the article body, repeated dozens of times per speech. The Fed
scraper now strips this at collection time (fed_speeches._strip_footnote_noise);
this one-off cleans the rows scraped before that fix: it rewrites raw_text,
recomputes content_hash (the dedup key, so future re-scrapes still dedupe), and
sets model_version -> NULL so step 3 re-embeds/re-scores them on the clean text.

    python scripts/clean_footnote_boilerplate.py
    python scripts/run_phase1.py --steps 3,4    # re-score cleaned rows + rebuild signals
    python scripts/cluster_speeches.py          # re-cluster on clean embeddings
"""

import sys

sys.path.insert(0, ".")

from loguru import logger
from sqlalchemy import select, text, update

from sentiment_signal.collectors.base import BaseScraper
from sentiment_signal.collectors.fed_speeches import _strip_footnote_noise
from sentiment_signal.db.models import Statement, StatementAnalysis
from sentiment_signal.db.session import SessionLocal
from sentiment_signal.utils.terminal import progress


def main() -> None:
    session = SessionLocal()
    try:
        rows = session.execute(select(Statement.id, Statement.raw_text)).all()
        logger.info(f"Scanning {len(rows)} statements for footnote boilerplate…")
        cleaned = skipped = 0
        for sid, raw in progress(rows, "clean_boilerplate", every=500):
            new = _strip_footnote_noise(raw)
            if new == raw:
                continue
            new_hash = BaseScraper.content_hash(new)
            # Guard against a (very unlikely) hash collision with another row
            clash = session.scalar(
                select(Statement.id).where(Statement.content_hash == new_hash, Statement.id != sid)
            )
            if clash:
                logger.warning(f"{sid}: cleaned hash collides with {clash}, skipping")
                skipped += 1
                continue
            session.execute(
                update(Statement)
                .where(Statement.id == sid)
                .values(raw_text=new, content_hash=new_hash)
            )
            session.execute(
                update(StatementAnalysis)
                .where(StatementAnalysis.statement_id == sid)
                .values(model_version=None)  # flag for re-score on clean text
            )
            cleaned += 1
            if cleaned % 200 == 0:
                session.commit()
        session.commit()

        remaining = session.execute(
            text("select count(*) from statements where lower(raw_text) like '%return to text%'")
        ).scalar()
        logger.info(
            f"Cleaned {cleaned} statements ({skipped} skipped); flagged for re-score. "
            f"Remaining with 'return to text': {remaining}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
