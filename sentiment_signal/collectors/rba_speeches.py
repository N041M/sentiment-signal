"""Scraper for Reserve Bank of Australia speech archive.

Year-based listing at: https://www.rba.gov.au/speeches/{year}/
Individual speech pages use semantic HTML — no JS rendering required.
"""

from __future__ import annotations

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
from sentiment_signal.utils.terminal import progress

BASE_URL = "https://www.rba.gov.au"
LISTING_URL = "https://www.rba.gov.au/speeches/{year}/"
REQUEST_DELAY = 1.0


class RBASpeechesScraper(BaseScraper):
    name = "rba_speeches"
    version = "0.1.0"

    def __init__(
        self, session: Session, start_year: int = 2015, end_year: int | None = None
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.end_year = end_year or datetime.now().year
        self.client = httpx.Client(
            headers={"User-Agent": "curl/8.7.1"},
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        for year in range(self.start_year, self.end_year + 1):
            logger.info(f"RBA speeches: fetching {year} listing")
            entries = self._fetch_listing(year)
            logger.info(f"RBA speeches {year}: {len(entries)} entries")
            for title, url, speaker, date in progress(entries, f"rba_speeches {year}"):
                if self.session.scalar(select(Statement).where(Statement.url == url)):
                    continue
                text = self._fetch_speech_text(url)
                time.sleep(REQUEST_DELAY)
                if not text or len(text) < 100:
                    continue
                items.append(
                    RawItem(
                        raw_text=text,
                        url=url,
                        published_at=date,
                        source_type="speech",
                        person_name=speaker,
                        platform="rba.gov.au",
                        metadata={"title": title},
                    )
                )
        return items

    def _fetch_listing(self, year: int) -> list[tuple[str, str, str, datetime]]:
        try:
            resp = self.client.get(LISTING_URL.format(year=year))
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(f"RBA speeches: listing failed for {year}: {exc}")
            return []
        return _parse_listing(resp.text)

    def _fetch_speech_text(self, url: str) -> str:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug(f"RBA speeches: fetch failed {url}: {exc}")
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()
        content = (
            soup.find("div", class_="article-content")
            or soup.find("div", id="content")
            or soup.find("article")
        )
        return (content or soup).get_text(separator=" ", strip=True)

    def _persist(self, items: list[RawItem]) -> int:
        if self._person_cache is None:
            self._person_cache = list(self.session.scalars(select(Person)).all())
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", self._person_cache)
            if person is None:
                logger.debug(f"RBA speeches: no match for '{item.person_name}'")
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


def _parse_listing(html: str) -> list[tuple[str, str, str, datetime]]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for article in soup.select(".rss-speech-item"):  # article (2021+) or div (pre-2021)
        try:
            link = article.select_one("a.rss-speech-html")
            if not link:
                continue
            url = BASE_URL + link["href"]
            title = link.get_text(strip=True)

            time_tag = article.select_one("time")
            date_str = time_tag["datetime"] if time_tag and time_tag.get("datetime") else ""
            date = _parse_date(date_str)
            if date is None:
                continue

            speaker_tag = article.select_one("strong.rss-speech-speaker")
            speaker = speaker_tag.get_text(strip=True) if speaker_tag else ""

            results.append((title, url, speaker, date))
        except Exception:
            continue
    return results


def _parse_date(date_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt[: len(fmt.replace("%z", ""))])
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, ".")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2015)
    args = parser.parse_args()
    from sentiment_signal.db.session import SessionLocal

    session = SessionLocal()
    scraper = RBASpeechesScraper(session, start_year=args.start_year)
    total = scraper.run()
    print(f"Inserted {total} new RBA speeches.")
    session.close()
