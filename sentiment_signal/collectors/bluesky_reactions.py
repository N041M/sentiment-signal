"""Bluesky reactions gatherer (architecture_v2 Stage 1B). Inert without creds.

Auth via an app password (Bluesky → Settings → App Passwords). Uses AT Protocol
`searchPosts` to find posts mentioning a speaker within the reaction window — direct,
time-bounded, statement-linkable (link_confidence 2 = speaker + time). Set
BLUESKY_HANDLE / BLUESKY_APP_PASSWORD in .env, then:
    python -m sentiment_signal.collectors.bluesky_reactions
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

XRPC = "https://bsky.social/xrpc"


class BlueskyReactionsScraper(BaseReactionScraper):
    name = "bluesky_reactions"
    version = "0.1.0"

    def __init__(self, session, **kwargs) -> None:
        super().__init__(session, **kwargs)
        self._client = httpx.Client(timeout=30, headers={"User-Agent": "SentimentSignal/0.1"})
        self._jwt: str | None = None

    def _available(self) -> bool:
        return bool(settings.bluesky_handle and settings.bluesky_app_password)

    def _auth(self) -> str:
        if self._jwt is None:
            resp = self._client.post(
                f"{XRPC}/com.atproto.server.createSession",
                json={
                    "identifier": settings.bluesky_handle,
                    "password": settings.bluesky_app_password,
                },
            )
            resp.raise_for_status()
            self._jwt = resp.json()["accessJwt"]
        return self._jwt

    def _search(self, statement_id, statement_url, speaker, since, until) -> list[RawItem]:
        resp = self._client.get(
            f"{XRPC}/app.bsky.feed.searchPosts",
            params={
                "q": f'"{speaker}"',
                "limit": self.per_statement_limit,
                "since": to_iso_z(since),
                "until": to_iso_z(until),
                "sort": "latest",
            },
            headers={"Authorization": f"Bearer {self._auth()}"},
        )
        resp.raise_for_status()
        items: list[RawItem] = []
        for post in resp.json().get("posts", []):
            record = post.get("record", {})
            text = (record.get("text") or "").strip()
            created = parse_iso8601(record.get("createdAt"))
            if created is None or len(text) < 15:
                continue
            handle = post.get("author", {}).get("handle", "")
            rkey = post.get("uri", "").rsplit("/", 1)[-1]
            items.append(
                self._reaction(
                    statement_id=statement_id,
                    text=text,
                    url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                    created=created,
                    net_score=post.get("likeCount", 0),
                    link_confidence=2,
                    platform="bluesky",
                )
            )
        return items


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    print(f"Inserted {BlueskyReactionsScraper(session).run()} Bluesky reactions.")
    session.close()
