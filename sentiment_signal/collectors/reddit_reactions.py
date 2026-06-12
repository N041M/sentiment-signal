"""Reddit reactions gatherer (architecture_v2 Stage 1B). Inert without creds.

NB: Reddit removed self-serve API access (manual review only as of 2025), so this stays
a creds-gated scaffold until/unless approved. When creds exist, it searches Reddit per
recent un-reacted statement within the window (link_confidence 2 = speaker + time, or 1
if the statement URL appears). Set REDDIT_CLIENT_ID / _SECRET in .env, then:
    python -m sentiment_signal.collectors.reddit_reactions
"""

from __future__ import annotations

from datetime import UTC, datetime

from sentiment_signal.collectors.base import RawItem
from sentiment_signal.collectors.base_reactions import BaseReactionScraper
from sentiment_signal.config import settings

SEARCH_SCOPE = "all"  # narrow to e.g. "economics+finance+politics" once tuned


class RedditReactionsScraper(BaseReactionScraper):
    name = "reddit_reactions"
    version = "0.2.0"

    def __init__(self, session, **kwargs) -> None:
        super().__init__(session, **kwargs)
        self._reddit = None

    def _available(self) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def _client(self):
        if self._reddit is None:
            import praw

            self._reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
                check_for_async=False,
            )
        return self._reddit

    def _search(self, statement_id, statement_url, speaker, since, until) -> list[RawItem]:
        results = (
            self._client()
            .subreddit(SEARCH_SCOPE)
            .search(f'"{speaker}"', sort="new", time_filter="year", limit=self.per_statement_limit)
        )
        items: list[RawItem] = []
        for sub in results:
            created = datetime.fromtimestamp(sub.created_utc, tz=UTC)
            text = f"{sub.title}\n{sub.selftext or ''}".strip()
            if not (since <= created <= until) or len(text) < 20:
                continue
            blob = (sub.selftext or "") + (getattr(sub, "url", "") or "")
            items.append(
                self._reaction(
                    statement_id=statement_id,
                    text=text,
                    url=f"https://reddit.com{sub.permalink}",
                    created=created,
                    net_score=getattr(sub, "score", 0),
                    link_confidence=1 if (statement_url and statement_url in blob) else 2,
                    platform="reddit",
                )
            )
        return items


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    print(f"Inserted {RedditReactionsScraper(session).run()} Reddit reactions.")
    session.close()
