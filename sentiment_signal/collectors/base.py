from __future__ import annotations

import hashlib
import re
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session

# C0 control characters except tab (\x09), newline (\x0a), carriage return (\x0d).
# PostgreSQL TEXT cannot store NUL (0x00); some scraped PDFs/government docs embed it.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow() is deprecated in 3.12+)."""
    return datetime.now(UTC)


@dataclass
class RawItem:
    raw_text: str
    url: str
    published_at: datetime
    source_type: str
    person_name: str | None = None
    platform: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseScraper(ABC):
    name: str = "base"
    version: str = "0.1.0"

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def content_hash(text: str) -> str:
        normalised = " ".join(text.lower().split())
        return hashlib.sha256(normalised.encode()).hexdigest()

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip control characters (incl. NUL) that PostgreSQL TEXT rejects."""
        return _CONTROL_CHARS.sub("", text)

    @abstractmethod
    def collect(self) -> list[RawItem]: ...

    def run(self) -> int:
        """Execute the scraper; return count of newly inserted items."""
        from sentiment_signal.db.models import CollectionRun, ScraperError

        run = CollectionRun(scraper_name=self.name, started_at=_utcnow(), status="running")
        self.session.add(run)
        self.session.commit()

        try:
            items = self.collect()
            inserted = self._persist(items)
            run.items_collected = len(items)
            run.items_deduplicated = len(items) - inserted
            run.finished_at = _utcnow()
            run.status = "success"
            self.session.commit()
            logger.info(f"{self.name}: {len(items)} collected, {inserted} new")
            return inserted
        except Exception as exc:
            run.status = "error"
            run.finished_at = _utcnow()
            err = ScraperError(
                scraper_name=self.name,
                error_message=str(exc),
                error_type=type(exc).__name__,
                stack_trace=traceback.format_exc(),
            )
            self.session.add(err)
            self.session.commit()
            logger.error(f"{self.name} failed: {exc}")
            return 0

    def _persist(self, items: list[RawItem]) -> int:
        """Insert items, skip duplicates via content_hash. Returns inserted count."""
        raise NotImplementedError("Subclasses should implement _persist or use a shared helper")
