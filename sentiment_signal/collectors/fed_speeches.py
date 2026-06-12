"""Scraper for the Federal Reserve speech archive.

Fetches speeches back to a configurable start year from:
  https://www.federalreserve.gov/apps/speech/speeches.aspx

Each speech page is fetched and parsed for full text. Speakers are resolved
against the persons table by matching aliases. Unresolvable speakers are
skipped with a warning — do not create phantom person rows.

Usage (standalone):
    python -m sentiment_signal.collectors.fed_speeches --start-year 2015
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
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
from sentiment_signal.utils.terminal import progress

LISTING_URL = "https://www.federalreserve.gov/newsevents/speech/{year}-speeches.htm"
BASE_URL = "https://www.federalreserve.gov"
REQUEST_DELAY = 1.5  # seconds between requests — be polite


@dataclass
class SpeechMeta:
    title: str
    speaker: str
    date: datetime
    url: str


class FedSpeechesScraper(BaseScraper):
    name = "fed_speeches"
    version = "0.1.0"

    def __init__(
        self, session: Session, start_year: int = 2015, end_year: int | None = None
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.end_year = end_year or datetime.now().year
        self.client = httpx.Client(
            headers={"User-Agent": "SentimentSignal/0.1 academic research"},
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: dict[str, Person] | None = None

    # ── Public ────────────────────────────────────────────────────────────────

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        for year in range(self.start_year, self.end_year + 1):
            metas = self._fetch_listing(year)
            logger.info(f"fed_speeches {year}: {len(metas)} speeches")
            for meta in progress(metas, f"fed_speeches {year}"):
                item = self._fetch_speech(meta)
                time.sleep(REQUEST_DELAY)
                if item:
                    items.append(item)
        return items

    # ── Listing page ──────────────────────────────────────────────────────────

    def _fetch_listing(self, year: int) -> list[SpeechMeta]:
        url = LISTING_URL.format(year=year)
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(f"fed_speeches: listing request failed for {year}: {exc}")
            return []
        return _parse_listing(resp.text)

    # ── Individual speech page ────────────────────────────────────────────────

    def _fetch_speech(self, meta: SpeechMeta) -> RawItem | None:
        # Skip if already in DB
        existing = self.session.scalar(select(Statement).where(Statement.url == meta.url))
        if existing:
            return None

        try:
            resp = self.client.get(meta.url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(f"fed_speeches: speech fetch failed {meta.url}: {exc}")
            return None

        text = _extract_speech_text(resp.text)
        if not text or len(text) < 100:
            logger.debug(f"fed_speeches: skipping short/empty speech {meta.url}")
            return None

        return RawItem(
            raw_text=text,
            url=meta.url,
            published_at=meta.date,
            source_type="speech",
            person_name=meta.speaker,
            platform="federalreserve.gov",
            metadata={"title": meta.title, "statement_subtype": "prepared_remarks"},
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist(self, items: list[RawItem]) -> int:
        persons = self._load_persons()
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", persons)
            if person is None:
                logger.debug(f"fed_speeches: no person match for '{item.person_name}', skipping")
                continue

            content_hash = self.content_hash(item.raw_text)
            stmt_insert = (
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
            result = self.session.execute(stmt_insert)
            if result.rowcount:
                inserted += 1
        self.session.commit()
        return inserted

    def _load_persons(self) -> list[Person]:
        if self._person_cache is None:
            self._person_cache = {
                p.canonical_name: p for p in self.session.scalars(select(Person)).all()
            }
        return list(self._person_cache.values())


# ── HTML parsing helpers ──────────────────────────────────────────────────────


def _parse_listing(html: str) -> list[SpeechMeta]:
    """Extract speech metadata from the Fed annual listing page.

    Page structure (as of 2024):
      div.eventlist__time > time   (format: M/D/YYYY)
      div.eventlist__event > p > a[href*="/newsevents/speech/"]  (title)
      div.eventlist__event > p.news__speaker  (speaker name)
    """
    soup = BeautifulSoup(html, "html.parser")
    metas: list[SpeechMeta] = []

    for event_div in soup.select("div.eventlist__event"):
        try:
            link = event_div.find("a", href=re.compile(r"/newsevents/speech/"))
            if not link:
                continue
            href = link["href"]
            url = href if href.startswith("http") else BASE_URL + href
            title = link.get_text(strip=True)

            # Date lives in the sibling eventlist__time div
            time_div = event_div.find_previous_sibling(
                class_="eventlist__time"
            ) or event_div.parent.find("div", class_="eventlist__time")
            date_tag = time_div.find("time") if time_div else None
            date = _parse_date(date_tag.get_text(strip=True)) if date_tag else None
            if date is None:
                continue

            # Speaker is in <p class="news__speaker">
            speaker_tag = event_div.find("p", class_="news__speaker")
            speaker = (
                speaker_tag.get_text(strip=True) if speaker_tag else _extract_speaker_from_url(href)
            )

            metas.append(SpeechMeta(title=title, speaker=speaker, date=date, url=url))
        except Exception:
            continue

    return metas


# Fed speech HTML embeds footnote/nav anchors inside the article body: each
# footnote ends with a "Return to text" back-link, and citations carry "(PDF)" /
# "(HTML)" link labels. Repeated dozens of times per speech (up to ~50x), this
# boilerplate dominates the TF-IDF cluster labels and dilutes the FinBERT
# embedding/score, so strip it from the extracted body.
_FOOTNOTE_NOISE = re.compile(
    r"\s*(?:Return to text|\(PDF\)|\(HTML\)|Accessible Version)\s*", re.IGNORECASE
)


def _strip_footnote_noise(text: str) -> str:
    """Remove repeated Fed footnote/nav boilerplate from extracted speech text."""
    return re.sub(r"\s{2,}", " ", _FOOTNOTE_NOISE.sub(" ", text)).strip()


def _extract_speech_text(html: str) -> str:
    """Extract main body text from an individual Fed speech HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove navigation, headers, footers
    for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    # Fed speeches typically live inside #article or .col-xs-12.col-sm-8
    article = (
        soup.find(id="article")
        or soup.find("div", class_=re.compile(r"col-xs-12.*col-sm-8", re.I))
        or soup.find("div", class_="speech-content")
        or soup.find("main")
    )
    body = (
        article.get_text(separator=" ", strip=True)
        if article
        else soup.get_text(separator=" ", strip=True)
    )
    return _strip_footnote_noise(body)


def _parse_date(date_str: str) -> datetime | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _extract_speaker_from_url(href: str) -> str:
    """Best-effort speaker extraction from Fed URL slug, e.g. /powell20230707a."""
    match = re.search(r"/([a-z]+)\d{8}", href.lower())
    return match.group(1).title() if match else ""


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Fed speech archive")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    scraper = FedSpeechesScraper(session, start_year=args.start_year, end_year=args.end_year)
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
