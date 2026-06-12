"""Scraper for BIS central bankers' speeches RSS feed.

Covers ECB, Bank of England, Bank of Japan, Bundesbank, SNB, RBA, and
~60 other central banks in a single feed — no authentication required.

Feed: https://www.bis.org/doclist/cbspeeches.rss
"""

from __future__ import annotations

import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sentiment_signal.collectors._resolve import resolve_person
from sentiment_signal.collectors.base import BaseScraper, RawItem
from sentiment_signal.db.models import Person, Statement
from sentiment_signal.utils.terminal import progress

RSS_URL = "https://www.bis.org/doclist/cbspeeches.rss"
REQUEST_DELAY = 1.0


class BISSpeechesScraper(BaseScraper):
    name = "bis_speeches"
    version = "0.1.0"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.client = httpx.Client(
            headers={"User-Agent": "SentimentSignal/0.1 academic research"},
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        logger.info("BIS speeches: fetching RSS feed")
        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            logger.warning("BIS speeches: empty feed")
            return []

        logger.info(f"BIS speeches: {len(feed.entries)} entries in feed")
        items: list[RawItem] = []
        for entry in progress(feed.entries, "bis_speeches"):
            item = self._process_entry(entry)
            if item:
                items.append(item)
            time.sleep(REQUEST_DELAY)
        return items

    def _process_entry(self, entry: feedparser.FeedParserDict) -> RawItem | None:
        url = entry.get("link", "")
        if not url:
            return None

        # Skip if already stored
        if self.session.scalar(select(Statement).where(Statement.url == url)):
            return None

        # Parse date
        date = self._parse_entry_date(entry)
        if date is None:
            return None

        # Fetch full speech text from the HTML page
        text = self._fetch_speech_text(url)
        if not text or len(text) < 100:
            return None

        speaker = entry.get("cb_nameaswritten") or entry.get("author", "")
        institution = entry.get("cb_institutionabbrev", "")

        return RawItem(
            raw_text=text,
            url=url,
            published_at=date,
            source_type="speech",
            person_name=speaker,
            platform=f"bis.org ({institution})",
        )

    def _fetch_speech_text(self, url: str) -> str:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug(f"BIS speeches: fetch failed {url}: {exc}")
            return ""
        return _extract_text(resp.text)

    @staticmethod
    def _parse_entry_date(entry: feedparser.FeedParserDict) -> datetime | None:
        # Prefer cb_occurrencedate (structured), fall back to updated
        occ = entry.get("cb_occurrencedate", "")
        if occ:
            try:
                return datetime.fromisoformat(occ.replace("Z", "+00:00"))
            except ValueError:
                pass
        updated = entry.get("updated", "")
        if updated:
            try:
                return parsedate_to_datetime(updated)
            except Exception:
                pass
        return None

    def _persist(self, items: list[RawItem]) -> int:
        if self._person_cache is None:
            self._person_cache = list(self.session.scalars(select(Person)).all())
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", self._person_cache)
            if person is None:
                logger.debug(f"BIS speeches: no match for '{item.person_name}', skipping")
                continue
            content_hash = self.content_hash(item.raw_text)
            result = self.session.execute(
                insert(Statement)
                .values(
                    person_id=person.id,
                    source_type=item.source_type,
                    raw_text=item.raw_text,
                    content_hash=content_hash,
                    url=item.url,
                    published_at=item.published_at,
                    influence_tier=person.influence_tier,
                    is_processed=False,
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            if result.rowcount:
                inserted += 1
        self.session.commit()
        return inserted


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    article = (
        soup.find("div", class_="article-box")
        or soup.find("div", id="extrawrapper")
        or soup.find("main")
        or soup.find("article")
    )
    return (article or soup).get_text(separator=" ", strip=True)


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    scraper = BISSpeechesScraper(session)
    total = scraper.run()
    print(f"Inserted {total} new BIS speeches.")
    session.close()
