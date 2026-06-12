"""Scraper for NATO Secretary General speeches and statements.

Source: https://www.nato.int/cps/en/natohq/opinions.htm
        Covers Stoltenberg (2014-2023) and Rutte (2023-present).

NATO speeches are directly relevant to war-related market signals:
Ukraine war updates, defence spending decisions, Article 5 invocations,
sanctions coordination, and alliance expansion (Finland, Sweden).

Usage:
    python -m sentiment_signal.collectors.nato_speeches
    python -m sentiment_signal.collectors.nato_speeches --start-year 2022
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

BASE_URL = "https://www.nato.int"
# NATO listing: sorted by date descending, page param increments by 1
LISTING_URL = "https://www.nato.int/cps/en/natohq/opinions.htm?selectedLocale=en&page={page}"
REQUEST_DELAY = 2.0


class NATOSpeechesScraper(BaseScraper):
    name = "nato_speeches"
    version = "0.1.0"

    def __init__(self, session: Session, start_year: int = 2015) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (academic research)"},
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        # nato.int/cps/en/natohq/opinions.htm is JavaScript-rendered. The 275 KB HTML
        # response contains only the React shell; all speech listings are fetched
        # client-side. No server-side RSS feed exists for SG opinions. Requires Playwright:
        #   `playwright install chromium && pip install playwright`
        # Until then, NATO content is partially covered by news coverage in the UN News
        # RSS feeds (peace-and-security topic) and BIS RSS.
        logger.warning(
            "nato_speeches: nato.int is JS-rendered; no opinion links in HTML response. "
            "Requires Playwright for scraping. Skipping."
        )
        return []

        items: list[RawItem] = []
        page = 1
        cutoff_hit = False

        while not cutoff_hit:
            url = LISTING_URL.format(page=page)
            logger.info(f"nato_speeches: fetching listing page {page}")
            try:
                resp = self.client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(f"nato_speeches: listing failed page {page}: {exc}")
                break

            entries = _parse_listing(resp.text)
            if not entries:
                break

            for entry in entries:
                if entry["date"].year < self.start_year:
                    cutoff_hit = True
                    break

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
                    logger.warning(f"nato_speeches: article fetch failed {entry['url']}: {exc}")
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
                        platform="nato.int",
                        metadata={
                            "title": entry["title"],
                            "statement_subtype": "nato_statement",
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
                # Fallback: any NATO institution match
                person = next((p for p in persons if "NATO" in (p.institution or "")), None)
            if person is None:
                logger.debug(f"nato_speeches: no person match for '{item.person_name}', skipping")
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
    """Extract entry metadata from a NATO opinions listing page.

    NATO listing structure (verified 2024):
      ul.lister > li
        time[datetime]          (ISO date)
        a[href] > span.title    (title)
        span.type               (speech / statement / etc)
        span.person             (speaker name, if present)
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []

    for li in soup.select("ul.lister li, div.lister-item, article.list-item"):
        try:
            link = li.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True)

            time_tag = li.find("time")
            if time_tag and time_tag.get("datetime"):
                date = _parse_date(time_tag["datetime"])
            else:
                date_tag = li.find(class_=re.compile(r"date|time", re.I))
                date = _parse_date(date_tag.get_text(strip=True)) if date_tag else None

            if not date:
                continue

            speaker_tag = li.find(class_=re.compile(r"person|speaker|author", re.I))
            if speaker_tag:
                speaker = speaker_tag.get_text(strip=True)
            else:
                # Infer from date: Rutte took over October 2023
                speaker = (
                    "Mark Rutte"
                    if date.year >= 2024 or (date.year == 2023 and date.month >= 10)
                    else "Jens Stoltenberg"
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
        soup.find("div", class_=re.compile(r"article|content|body|speech|text", re.I))
        or soup.find("article")
        or soup.find("main")
    )
    if article:
        return article.get_text(separator=" ", strip=True)
    return soup.get_text(separator=" ", strip=True)


def _parse_date(s: str) -> datetime | None:
    s = re.sub(r"\s+", " ", s.strip())
    for fmt in ("%Y-%m-%d", "%d %b. %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Handle ISO with time component
    try:
        return datetime.fromisoformat(s[:10])
    except ValueError:
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape NATO Secretary General speeches")
    parser.add_argument("--start-year", type=int, default=2015)
    args = parser.parse_args()

    session = SessionLocal()
    scraper = NATOSpeechesScraper(session, start_year=args.start_year)
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
