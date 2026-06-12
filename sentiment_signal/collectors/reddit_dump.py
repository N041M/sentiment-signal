"""Offline Reddit archive-dump ingester (architecture_v2 Stage 1B backfill).

Streams Arctic Shift / Pushshift-style per-subreddit NDJSON .zst dumps (the standard
academic route since Reddit closed self-serve API access) and links posts/comments to
statements: a line becomes a reaction when a speaker's **canonical full name** appears
in its text and its timestamp falls inside that statement's reaction window. Aliases
(bare surnames like "Cook", "Powell") are deliberately excluded — far too many false
positives in forum text. link_confidence 2 (name + time proximity).

Dumps end ~2024 — this is the historical backfill; live capture comes from the
HN/Bluesky/YouTube gatherers.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.collectors.base import BaseScraper
from sentiment_signal.config import settings
from sentiment_signal.db.models import Person, Reaction, Statement

PRE_WINDOW_HOURS = 2  # mirror BaseReactionScraper: window opens slightly before publish
BATCH = 1000
HEARTBEAT_LINES = 250_000


@dataclass
class SpeakerIndex:
    """Compiled name pattern + per-speaker statement windows (epoch seconds), sorted."""

    pattern: re.Pattern
    windows: dict[str, list[tuple[int, int, str]]]  # name -> [(start, end, statement_id)]


def build_index(rows: list[tuple[str, str, datetime]], window_hours: int) -> SpeakerIndex | None:
    """rows = [(statement_id, canonical_name, published_at)] -> matching index."""
    windows: dict[str, list[tuple[int, int, str]]] = {}
    for sid, name, published_at in rows:
        if not name:
            continue
        ts = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
        start = int((ts - timedelta(hours=PRE_WINDOW_HOURS)).timestamp())
        end = int((ts + timedelta(hours=window_hours)).timestamp())
        windows.setdefault(name.lower(), []).append((start, end, str(sid)))
    if not windows:
        return None
    for spans in windows.values():
        spans.sort()
    pattern = re.compile("|".join(re.escape(n) for n in sorted(windows, key=len, reverse=True)))
    return SpeakerIndex(pattern=pattern, windows=windows)


def match_line(text_lower: str, created: int, index: SpeakerIndex) -> list[str]:
    """Statement ids whose speaker is named in the text and whose window covers created."""
    sids: list[str] = []
    for name in {m.group(0) for m in index.pattern.finditer(text_lower)}:
        spans = index.windows[name]
        # candidate windows: those starting at/before `created`; scan back while open
        i = bisect.bisect_right(spans, (created, 2**62, "")) - 1
        while i >= 0:
            start, end, sid = spans[i]
            if end >= created:
                sids.append(sid)
            elif created - start > 60 * 60 * 24 * 14:
                break  # far past any plausible window; stop scanning earlier spans
            i -= 1
    return sids


def extract_text_url(obj: dict) -> tuple[str, str] | None:
    """NDJSON line object -> (text, url); None for deleted/empty/unusable lines."""
    if "body" in obj:  # comment
        text = (obj.get("body") or "").strip()
        permalink = obj.get("permalink") or ""
    else:  # submission
        title = (obj.get("title") or "").strip()
        selftext = (obj.get("selftext") or "").strip()
        if selftext in ("[deleted]", "[removed]"):
            selftext = ""
        text = f"{title}\n{selftext}".strip()
        permalink = obj.get("permalink") or ""
    if text in ("[deleted]", "[removed]") or len(text) < 20:
        return None
    url = (
        f"https://reddit.com{permalink}" if permalink else f"https://reddit.com/{obj.get('id', '')}"
    )
    return text, url


def ingest_dump(path: str, session, *, limit: int | None = None) -> int:
    """Stream one .zst NDJSON dump file; insert linked reactions. Returns inserted count."""
    import io

    import zstandard

    rows = session.execute(
        select(Statement.id, Person.canonical_name, Statement.published_at).join(
            Person, Person.id == Statement.person_id
        )
    ).all()
    index = build_index([(r[0], r[1], r[2]) for r in rows], settings.reaction_window_hours)
    if index is None:
        logger.error("No statements to link against — run the statement pipeline first")
        return 0
    logger.info(f"Index: {len(index.windows)} speakers, {len(rows)} statements. Streaming {path}…")

    inserted = lines = 0
    pending: list[dict] = []

    def flush() -> int:
        nonlocal pending
        if not pending:
            return 0
        result = session.execute(
            insert(Reaction).values(pending).on_conflict_do_nothing(index_elements=["content_hash"])
        )
        session.commit()
        n = result.rowcount or 0
        pending = []
        return n

    with open(path, "rb") as fh:
        reader = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(fh)
        for line in io.TextIOWrapper(reader, encoding="utf-8", errors="ignore"):
            lines += 1
            if lines % HEARTBEAT_LINES == 0:
                logger.info(f"ingest: {lines:,} lines, {inserted} reactions so far")
            if limit and lines > limit:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            created = obj.get("created_utc")
            if created is None:
                continue
            created = int(float(created))
            extracted = extract_text_url(obj)
            if extracted is None:
                continue
            text, url = extracted
            sids = match_line(text.lower(), created, index)
            if not sids:
                continue
            clean = BaseScraper.clean_text(text)
            for sid in sids:
                pending.append(
                    dict(
                        statement_id=sid,
                        link_confidence=2,
                        platform="reddit_archive",
                        raw_text=clean,
                        content_hash=BaseScraper.content_hash(f"{sid}:{clean}"),
                        published_at=datetime.fromtimestamp(created, tz=UTC),
                        net_score=int(obj.get("score") or 0),
                        is_processed=False,
                    )
                )
            if len(pending) >= BATCH:
                inserted += flush()
    inserted += flush()
    logger.info(f"ingest done: {lines:,} lines read, {inserted} reactions inserted")
    return inserted
