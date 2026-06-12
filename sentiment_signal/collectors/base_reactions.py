"""Shared base for reaction gatherers (architecture_v2 Stage 1B — public opinion).

All platforms share the same job: for each recent statement with no reactions yet,
search the platform within the reaction window for posts/comments referencing the
speaker, and store matches in the `reactions` table (deduped, point-in-time). The only
per-platform differences are auth and the search call — so a new source (Reddit,
StockTwits, …) is just an `_available()` + `_search()` pair, no plumbing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.collectors.base import BaseScraper, RawItem
from sentiment_signal.config import settings
from sentiment_signal.db.models import Person, Reaction, Statement


def parse_iso8601(s: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (accepting a trailing 'Z') to tz-aware UTC."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def to_iso_z(dt: datetime) -> str:
    """UTC ISO-8601 with a 'Z' suffix (the form most platform search APIs expect)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class BaseReactionScraper(BaseScraper):
    """Platform-agnostic reaction gathering. Subclasses implement `_available()` and
    `_search(statement_id, statement_url, speaker, since, until) -> list[RawItem]`.
    """

    def __init__(
        self, session, *, max_statements: int = 200, per_statement_limit: int = 25
    ) -> None:
        super().__init__(session)
        self.max_statements = max_statements
        self.per_statement_limit = per_statement_limit

    # --- subclass hooks -------------------------------------------------------
    def _available(self) -> bool:
        raise NotImplementedError

    def _search(self, statement_id, statement_url, speaker, since, until) -> list[RawItem]:
        raise NotImplementedError

    # --- shared helpers -------------------------------------------------------
    def _reaction(
        self, *, statement_id, text, url, created, net_score, link_confidence, platform
    ) -> RawItem:
        return RawItem(
            raw_text=self.clean_text(text),
            url=url,
            published_at=created,
            source_type="reaction",
            person_name=None,
            platform=platform,
            metadata={
                "statement_id": str(statement_id),
                "link_confidence": link_confidence,
                "net_score": int(net_score or 0),
            },
        )

    def collect(self) -> list[RawItem]:
        if not self._available():
            logger.warning(f"{self.name}: no creds in .env — skipping (Phase 2)")
            return []
        window = timedelta(hours=settings.reaction_window_hours)
        statements = self.session.execute(
            select(Statement.id, Statement.url, Statement.published_at, Person.canonical_name)
            .join(Person, Person.id == Statement.person_id)
            .outerjoin(Reaction, Reaction.statement_id == Statement.id)
            .where(Reaction.id.is_(None))
            .order_by(Statement.published_at.desc())
            .limit(self.max_statements)
        ).all()

        items: list[RawItem] = []
        for sid, url, published_at, speaker in statements:
            if not speaker:
                continue
            since, until = published_at - timedelta(hours=2), published_at + window
            try:
                items.extend(self._search(sid, url, speaker, since, until))
            except Exception as exc:  # one source/statement failure must not abort the run
                logger.debug(f"{self.name}: search failed for '{speaker}': {exc}")
        return items

    def _persist(self, items: list[RawItem]) -> int:
        inserted = 0
        for it in items:
            result = self.session.execute(
                insert(Reaction)
                .values(
                    statement_id=it.metadata["statement_id"],
                    link_confidence=it.metadata.get("link_confidence", 3),
                    platform=it.platform or self.name,
                    raw_text=it.raw_text,
                    content_hash=self.content_hash(it.raw_text),
                    published_at=it.published_at,
                    net_score=it.metadata.get("net_score", 0),
                    is_processed=False,
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            inserted += result.rowcount
        self.session.commit()
        return inserted
