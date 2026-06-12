"""Hacker News reactions gatherer (architecture_v2 Stage 1B). No credentials needed.

Uses the open Algolia HN search API (keyless, full history, timestamped) to find
stories/comments mentioning a speaker within the reaction window. link_confidence 2
(speaker + time proximity). Run:
    python -m sentiment_signal.collectors.hn_reactions
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx

from sentiment_signal.collectors.base import RawItem
from sentiment_signal.collectors.base_reactions import BaseReactionScraper

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
REQUEST_DELAY = 0.4  # polite; Algolia allows ~10k req/h


def hit_to_item(
    hit: dict, since: datetime, until: datetime
) -> tuple[str, str, datetime, int] | None:
    """Pure parser: Algolia hit -> (text, url, created, points), or None if unusable.

    Stories carry title/story_text; comments carry comment_text. Out-of-window or
    near-empty hits are dropped (the API filter should bound time already; re-check
    defensively).
    """
    created_i = hit.get("created_at_i")
    if created_i is None:
        return None
    created = datetime.fromtimestamp(int(created_i), tz=UTC)
    if not (since <= created <= until):
        return None
    if hit.get("comment_text"):
        text = hit["comment_text"]
    else:
        text = " ".join(p for p in (hit.get("title"), hit.get("story_text")) if p)
    text = text.strip()
    if len(text) < 15:
        return None
    url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
    return text, url, created, int(hit.get("points") or 0)


class HNReactionsScraper(BaseReactionScraper):
    name = "hn_reactions"
    version = "0.1.0"

    def __init__(self, session, **kwargs) -> None:
        super().__init__(session, **kwargs)
        self._client = httpx.Client(
            timeout=30, headers={"User-Agent": "SentimentSignal/0.1 academic research"}
        )

    def _available(self) -> bool:
        return True  # open API, no credentials

    def _search(self, statement_id, statement_url, speaker, since, until) -> list[RawItem]:
        resp = self._client.get(
            ALGOLIA_URL,
            params={
                "query": f'"{speaker}"',
                "tags": "(story,comment)",
                "hitsPerPage": self.per_statement_limit,
                "numericFilters": (
                    f"created_at_i>={int(since.timestamp())},created_at_i<={int(until.timestamp())}"
                ),
            },
        )
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        items: list[RawItem] = []
        for hit in resp.json().get("hits", []):
            parsed = hit_to_item(hit, since, until)
            if parsed is None:
                continue
            text, url, created, points = parsed
            items.append(
                self._reaction(
                    statement_id=statement_id,
                    text=text,
                    url=url,
                    created=created,
                    net_score=points,
                    link_confidence=2,
                    platform="hackernews",
                )
            )
        return items


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    print(f"Inserted {HNReactionsScraper(session).run()} HN reactions.")
    session.close()
