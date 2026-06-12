"""YouTube reactions gatherer (architecture_v2 Stage 1B). Inert without an API key.

Two-step: search videos about a speaker within the reaction window, then pull in-window
top-level comments as reactions (link_confidence 3 = topic/keyword — weaker than a direct
post match). Free YouTube Data API v3 key in .env (YOUTUBE_API_KEY). NB: search.list costs
100 quota units (10k/day free), so max_statements defaults low. Run:
    python -m sentiment_signal.collectors.youtube_reactions
"""

from __future__ import annotations

import httpx

from sentiment_signal.collectors.base import RawItem
from sentiment_signal.collectors.base_reactions import (
    BaseReactionScraper,
    parse_iso8601,
    to_iso_z,
)
from sentiment_signal.config import settings

API = "https://www.googleapis.com/youtube/v3"


class YouTubeReactionsScraper(BaseReactionScraper):
    name = "youtube_reactions"
    version = "0.1.0"

    def __init__(
        self,
        session,
        *,
        max_statements: int = 50,
        per_statement_limit: int = 20,
        videos_per_statement: int = 3,
    ) -> None:
        super().__init__(
            session, max_statements=max_statements, per_statement_limit=per_statement_limit
        )
        self.videos_per_statement = videos_per_statement
        self._client = httpx.Client(timeout=30)

    def _available(self) -> bool:
        return bool(settings.youtube_api_key)

    def _search(self, statement_id, statement_url, speaker, since, until) -> list[RawItem]:
        resp = self._client.get(
            f"{API}/search",
            params={
                "part": "snippet",
                "q": speaker,
                "type": "video",
                "order": "relevance",
                "publishedAfter": to_iso_z(since),
                "publishedBefore": to_iso_z(until),
                "maxResults": self.videos_per_statement,
                "key": settings.youtube_api_key,
            },
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for video in resp.json().get("items", []):
            vid = video.get("id", {}).get("videoId")
            if vid:
                items.extend(self._comments(statement_id, vid, since, until))
        return items

    def _comments(self, statement_id, video_id, since, until) -> list[RawItem]:
        try:
            resp = self._client.get(
                f"{API}/commentThreads",
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "order": "relevance",
                    "maxResults": self.per_statement_limit,
                    "key": settings.youtube_api_key,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []  # comments disabled / video gone
        items: list[RawItem] = []
        for thread in resp.json().get("items", []):
            snippet = thread["snippet"]["topLevelComment"]["snippet"]
            created = parse_iso8601(snippet.get("publishedAt"))
            text = (snippet.get("textDisplay") or "").strip()
            if created is None or not (since <= created <= until) or len(text) < 15:
                continue
            items.append(
                self._reaction(
                    statement_id=statement_id,
                    text=text,
                    url=f"https://youtube.com/watch?v={video_id}",
                    created=created,
                    net_score=snippet.get("likeCount", 0),
                    link_confidence=3,
                    platform="youtube",
                )
            )
        return items


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    print(f"Inserted {YouTubeReactionsScraper(session).run()} YouTube reactions.")
    session.close()
