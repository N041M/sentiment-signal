"""Scraper for UN news coverage of peace, security, and geopolitical statements.

Data source: UN News RSS feeds (https://news.un.org)
These RSS feeds are publicly accessible without authentication and cover:
  - Peace and security topics (conflicts, ceasefires, sanctions)
  - Regional coverage (Europe/Ukraine, Middle East, Africa)
  - Secretary-General statements and press briefings

Full article text is fetched from each RSS entry's link. Articles involving the
Secretary-General are attributed to Guterres; all others are attributed to the
UN News institution entry (influence_tier 2).

Because the SG speeches site (un.org/sg) returns 202 bot-challenge responses and
NATO/White House are JavaScript-rendered, UN News RSS is the primary geopolitical
feed for war-related content.

Usage:
    python -m sentiment_signal.collectors.un_sg_speeches
    python -m sentiment_signal.collectors.un_sg_speeches --start-year 2022
"""

from __future__ import annotations

import random
import re
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
from sentiment_signal.db.session import SessionLocal
from sentiment_signal.utils.terminal import progress

REQUEST_DELAY = 1.5
# Status codes that indicate transient throttling — worth retrying with backoff
_RETRY_STATUS = {406, 408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 4

# UN News RSS feeds covering geopolitical and war-related content
RSS_FEEDS = {
    "peace_security": "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml",
    "europe": "https://news.un.org/feed/subscribe/en/news/region/europe/feed/rss.xml",
    "middle_east": "https://news.un.org/feed/subscribe/en/news/region/middle-east/feed/rss.xml",
    "africa": "https://news.un.org/feed/subscribe/en/news/region/africa/feed/rss.xml",
    "americas": "https://news.un.org/feed/subscribe/en/news/region/americas/feed/rss.xml",
}

# Patterns that suggest SG authorship in an article
_SG_PATTERNS = [
    r"secretary.general",
    r"guterres",
    r"\bSG\b",
    r"UN chief",
    r"spokesperson for the secretary",
    r"spokesman for the secretary",
]
_SG_RE = re.compile("|".join(_SG_PATTERNS), re.IGNORECASE)


class UNSGSpeechesScraper(BaseScraper):
    name = "un_sg_speeches"
    version = "0.2.0"

    def __init__(
        self,
        session: Session,
        start_year: int = 2015,
        feeds: list[str] | None = None,
        fetch_full_text: bool = False,
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.feed_urls = feeds or list(RSS_FEEDS.values())
        self.fetch_full_text = fetch_full_text
        self.client = httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,*/*",
            },
            timeout=20,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        for feed_name, feed_url in RSS_FEEDS.items():
            if feed_url not in self.feed_urls:
                continue
            logger.info(f"un_news: fetching {feed_name} RSS")
            parsed = feedparser.parse(feed_url)
            if not parsed.entries:
                logger.warning(f"un_news: no entries from {feed_name}")
                continue

            logger.info(f"un_news: {len(parsed.entries)} entries in {feed_name}")
            for entry in progress(parsed.entries, f"un_news {feed_name}", every=10):
                # entry["link"] is a /feed/view/ redirect that returns 406.
                # entry["id"] is the canonical /en/story/ URL.
                url = entry.get("id", "") or entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                pub_date = _parse_rss_date(entry.get("published", ""))
                if not pub_date or pub_date.year < self.start_year:
                    continue

                existing = self.session.scalar(select(Statement).where(Statement.url == url))
                if existing:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")

                # Default: use title + summary from RSS (no HTTP fetch needed).
                # Pass --fetch-full-text to attempt fetching the article page instead.
                if self.fetch_full_text:
                    html = self._get_with_backoff(url)
                    text = _extract_article_text(html) if html else ""
                    if len(text) < 150:
                        text = f"{title}. {summary}"
                else:
                    text = f"{title}. {summary}"

                if not text or len(text) < 50:
                    continue

                # Attribute to SG if content mentions Guterres or Secretary-General
                speaker = (
                    "Antonio Guterres"
                    if _SG_RE.search(text) or _SG_RE.search(title)
                    else "United Nations"
                )

                items.append(
                    RawItem(
                        raw_text=text,
                        url=url,
                        published_at=pub_date,
                        source_type="statement",
                        person_name=speaker,
                        platform="news.un.org",
                        metadata={
                            "title": title,
                            "statement_subtype": f"un_news_{feed_name}",
                        },
                    )
                )

        logger.info(f"un_news: {len(items)} entries ready to persist")
        return items

    def _get_with_backoff(self, url: str) -> str | None:
        """GET with exponential backoff on transient throttling (406/429/5xx).

        The UN News CDN rate-limits bursts of sequential requests, returning 406
        intermittently. Backoff with jitter clears it without changing headers.
        """
        delay = REQUEST_DELAY
        for attempt in range(_MAX_RETRIES):
            time.sleep(delay)
            try:
                resp = self.client.get(url)
                if resp.status_code in _RETRY_STATUS:
                    delay = REQUEST_DELAY * (2**attempt) + random.uniform(0, 1.0)
                    logger.debug(
                        f"un_news: {resp.status_code} on {url[-30:]}, "
                        f"retry {attempt + 1}/{_MAX_RETRIES} in {delay:.1f}s"
                    )
                    continue
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as exc:
                delay = REQUEST_DELAY * (2**attempt) + random.uniform(0, 1.0)
                logger.debug(f"un_news: error on {url[-30:]}: {exc}, retry in {delay:.1f}s")
        logger.warning(f"un_news: gave up on {url} after {_MAX_RETRIES} retries")
        return None

    def _persist(self, items: list[RawItem]) -> int:
        persons = self._load_persons()

        # Warn once if UN persons are missing from the database
        un_persons = [
            p
            for p in persons
            if "United Nations" in (p.institution or "") or "Guterres" in (p.canonical_name or "")
        ]
        if not un_persons:
            logger.warning(
                "un_news: no UN persons found in the database. "
                "Run: python scripts/seed_geopolitical_persons.py"
            )

        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", persons)
            if person is None:
                person = next(
                    (p for p in persons if "United Nations" in (p.institution or "")), None
                )
            if person is None:
                logger.debug(f"un_news: no person match for '{item.person_name}', skipping")
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
                    statement_subtype=item.metadata.get("statement_subtype"),
                    is_processed=False,
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
            )
            if result.rowcount:
                inserted += 1
        self.session.commit()
        return inserted

    def _load_persons(self) -> list[Person]:
        if self._person_cache is None:
            self._person_cache = self.session.scalars(select(Person)).all()
        return list(self._person_cache)


def _extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside", "figure"]):
        tag.decompose()
    article = (
        soup.find("div", class_=re.compile(r"story-body|article-body|field-body|content", re.I))
        or soup.find("article")
        or soup.find("main")
    )
    if article:
        return re.sub(r"\s+", " ", article.get_text(separator=" ")).strip()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def _parse_rss_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape UN News RSS for geopolitical content")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument(
        "--feeds",
        nargs="+",
        choices=list(RSS_FEEDS.keys()),
        default=list(RSS_FEEDS.keys()),
        help="Which UN News RSS feeds to include",
    )
    parser.add_argument(
        "--fetch-full-text",
        action="store_true",
        help="Fetch full article text (slower; some articles return 406)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    feed_urls = [RSS_FEEDS[f] for f in args.feeds]
    scraper = UNSGSpeechesScraper(
        session,
        start_year=args.start_year,
        feeds=feed_urls,
        fetch_full_text=args.fetch_full_text,
    )
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
