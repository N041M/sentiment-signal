"""Scraper for IMF speeches and statements archive.

Source: https://www.imf.org/en/News/Articles?issuetype=speeches
Covers Managing Director speeches and senior staff statements from 2015 onwards.

Usage (standalone):
    python -m sentiment_signal.collectors.imf_speeches --start-year 2015
"""

from __future__ import annotations

import re
import time
from datetime import datetime

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

BASE_URL = "https://www.imf.org"
LISTING_URL = (
    "https://www.imf.org/en/News/Articles"
    "?startdate={start}&enddate={end}&issuetype=speeches&page={page}"
)
REQUEST_DELAY = 2.0


class IMFSpeechesScraper(BaseScraper):
    name = "imf_speeches"
    version = "0.1.0"

    def __init__(
        self, session: Session, start_year: int = 2015, end_year: int | None = None
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.end_year = end_year or datetime.now().year
        self.client = httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.imf.org/en/News",
            },
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        # IMF website returns HTTP 403 on all paths (Cloudflare WAF).
        # To scrape IMF speeches, install Playwright and replace this method with a
        # browser-based fetch: `playwright install chromium && pip install playwright`
        # Until then, IMF content reaches the corpus indirectly via the BIS RSS scraper,
        # which republishes speeches delivered at BIS events (including IMF MD speeches).
        logger.warning(
            "imf_speeches: imf.org blocks all non-browser HTTP clients (Cloudflare 403). "
            "Requires Playwright for full scraping. Skipping."
        )
        return []

        items: list[RawItem] = []
        start = f"01-01-{self.start_year}"
        end = f"12-31-{self.end_year}"
        page = 1

        while True:
            url = LISTING_URL.format(start=start, end=end, page=page)
            logger.info(f"imf_speeches: fetching listing page {page}")
            try:
                resp = self.client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(f"imf_speeches: listing failed page {page}: {exc}")
                break

            entries = _parse_listing(resp.text)
            if not entries:
                break

            for entry in entries:
                existing = self.session.scalar(
                    select(Statement).where(Statement.url == entry["url"])
                )
                if existing:
                    continue

                time.sleep(REQUEST_DELAY)
                try:
                    article_resp = self.client.get(entry["url"])
                    article_resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning(f"imf_speeches: article fetch failed {entry['url']}: {exc}")
                    continue

                text = _extract_article_text(article_resp.text)
                if not text or len(text) < 150:
                    continue

                items.append(
                    RawItem(
                        raw_text=text,
                        url=entry["url"],
                        published_at=entry["date"],
                        source_type="speech",
                        person_name=entry["speaker"],
                        platform="imf.org",
                        metadata={
                            "title": entry["title"],
                            "statement_subtype": "imf_speech",
                        },
                    )
                )

            page += 1
            time.sleep(REQUEST_DELAY)

        return items

    def _persist(self, items: list[RawItem]) -> int:
        persons = self._load_persons()
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", persons)
            if person is None:
                logger.debug(f"imf_speeches: no person match for '{item.person_name}', skipping")
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


def _parse_listing(html: str) -> list[dict]:
    """Extract article metadata from an IMF news listing page.

    IMF listing structure:
      div.imf-rss-item (or similar)  ->  h4 > a (title + href)
                                         span.date or time.date
                                         span.speaker or author block
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []

    # IMF uses a repeating article card; selectors verified against 2024 layout.
    for card in soup.select("div.imf-rss-item, article.imf-rss-item, div.news-item"):
        try:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            url = href if href.startswith("http") else BASE_URL + href
            title = link_tag.get_text(strip=True)

            date_tag = card.find(class_=re.compile(r"date|time", re.I)) or card.find("time")
            date = _parse_date(date_tag.get_text(strip=True)) if date_tag else None
            if not date:
                continue

            # Speaker is often in a byline or sub-heading
            speaker_tag = card.find(class_=re.compile(r"speaker|author|byline", re.I)) or card.find(
                "p"
            )
            speaker = speaker_tag.get_text(strip=True) if speaker_tag else ""
            # Strip role suffixes like "by Kristalina Georgieva, Managing Director"
            speaker = (
                re.sub(r"(?i)\b(by|remarks by|speech by)\b", "", speaker).split(",")[0].strip()
            )

            entries.append({"url": url, "title": title, "date": date, "speaker": speaker})
        except Exception:
            continue

    return entries


def _extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    article = (
        soup.find("div", class_=re.compile(r"article-body|content-body|entry-content|speech", re.I))
        or soup.find("main")
        or soup.find("article")
    )
    if article:
        return article.get_text(separator=" ", strip=True)
    return soup.get_text(separator=" ", strip=True)


def _parse_date(s: str) -> datetime | None:
    s = s.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape IMF speech archive")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    scraper = IMFSpeechesScraper(session, start_year=args.start_year, end_year=args.end_year)
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
