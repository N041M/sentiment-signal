#!/usr/bin/env python3
"""Backfill reactions from Arctic Shift / Pushshift-style Reddit .zst dumps.

Get per-subreddit dumps (submissions + comments) from Arctic Shift downloads or
Academic Torrents — good starter set: r/economics, r/investing, r/stocks,
r/wallstreetbets, r/politics, r/worldnews. Then:

    python scripts/ingest_reddit_dump.py path/to/economics_comments.zst [more.zst ...]
    python scripts/ingest_reddit_dump.py --limit 1000000 file.zst    # smoke-test run
"""

import argparse
import sys

sys.path.insert(0, ".")

from sentiment_signal.collectors.reddit_dump import ingest_dump
from sentiment_signal.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Reddit archive dumps as reactions")
    parser.add_argument("paths", nargs="+", help=".zst NDJSON dump files")
    parser.add_argument("--limit", type=int, default=None, help="max lines per file (smoke test)")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        total = sum(ingest_dump(p, session, limit=args.limit) for p in args.paths)
        print(f"Total reactions inserted: {total}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
