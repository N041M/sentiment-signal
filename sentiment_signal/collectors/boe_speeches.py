"""Scraper for Bank of England speeches RSS feed.

Dedicated BoE feed with ~50 most recent speeches; more granular than BIS.
Feed: https://www.bankofengland.co.uk/rss/speeches
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

RSS_URL = "https://www.bankofengland.co.uk/rss/speeches"
BASE_URL = "https://www.bankofengland.co.uk"
REQUEST_DELAY = 1.0


class BoESpeechesScraper(BaseScraper):
    name = "boe_speeches"
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
        logger.info("BoE speeches: fetching RSS feed")
        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            logger.warning("BoE speeches: empty feed")
            return []

        logger.info(f"BoE speeches: {len(feed.entries)} entries")
        items: list[RawItem] = []
        for entry in progress(feed.entries, "boe_speeches"):
            item = self._process_entry(entry)
            if item:
                items.append(item)
            time.sleep(REQUEST_DELAY)
        return items

    def _process_entry(self, entry: feedparser.FeedParserDict) -> RawItem | None:
        url = entry.get("link", "")
        if not url:
            return None
        if self.session.scalar(select(Statement).where(Statement.url == url)):
            return None

        date = _parse_date(entry.get("published", ""))
        if date is None:
            return None

        text = self._fetch_speech_text(url)
        if not text or len(text) < 100:
            return None

        title = entry.get("title", "")
        speaker = _extract_speaker(title, url)

        return RawItem(
            raw_text=text,
            url=url,
            published_at=date,
            source_type="speech",
            person_name=speaker,
            platform="bankofengland.co.uk",
        )

    def _fetch_speech_text(self, url: str) -> str:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug(f"BoE speeches: fetch failed {url}: {exc}")
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        article = (
            soup.find("div", class_="page-content") or soup.find("article") or soup.find("main")
        )
        return (article or soup).get_text(separator=" ", strip=True)

    def _persist(self, items: list[RawItem]) -> int:
        if self._person_cache is None:
            self._person_cache = list(self.session.scalars(select(Person)).all())
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", self._person_cache)
            if person is None:
                logger.debug(f"BoE speeches: no match for '{item.person_name}'")
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


def _extract_speaker(title: str, url: str) -> str:
    """Extract speaker name from BoE speech title or URL slug.

    Handles three patterns:
      1. "Title − speech by Andrew Bailey"   (em-dash or hyphen)
      2. "Andrew Bailey: Title here"
      3. URL slug: /2026/june/andrew-bailey-speech-at-...
    """
    import re

    # Pattern 1: "... speech by Name" / "... speech by Name, ..."
    m = re.search(r"speech by ([A-Z][a-zA-Z\s\-\.]+?)(?:,|$)", title)
    if m:
        return m.group(1).strip()

    # Pattern 2: "Name: ..."
    if ":" in title:
        candidate = title.split(":")[0].strip()
        if len(candidate.split()) <= 4:  # names are short; titles are longer
            return candidate

    # Pattern 3: extract from URL slug — /yyyy/month/first-last-speech-...
    m = re.search(r"/(\d{4}/\w+/)([\w-]+?)-(?:speech|slides?|remarks?|address)", url)
    if m:
        slug = m.group(2).replace("-", " ").title()
        return slug

    return ""


def _parse_date(date_str: str) -> datetime | None:
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


if __name__ == "__main__":
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    scraper = BoESpeechesScraper(session)
    total = scraper.run()
    print(f"Inserted {total} new BoE speeches.")
    session.close()
