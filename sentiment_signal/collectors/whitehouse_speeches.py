"""Scraper for White House speeches and press remarks.

Source: https://www.whitehouse.gov/briefing-room/speeches-remarks/
        https://www.whitehouse.gov/briefing-room/statements-releases/

Captures presidential speeches and official statements including those on wars,
sanctions, foreign policy, and geopolitical events that indirectly affect markets.

Usage:
    python -m sentiment_signal.collectors.whitehouse_speeches
    python -m sentiment_signal.collectors.whitehouse_speeches --start-year 2022
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

BASE_URL = "https://www.whitehouse.gov"
# WordPress REST API — returns JSON, supports pagination
WP_SPEECHES_API = (
    "https://www.whitehouse.gov/wp-json/wp/v2/posts"
    "?per_page=100&page={page}"
    "&categories=6"  # category 6 = Speeches & Remarks
)
WP_STATEMENTS_API = (
    "https://www.whitehouse.gov/wp-json/wp/v2/posts"
    "?per_page=100&page={page}"
    "&categories=4"  # category 4 = Statements & Releases
)
REQUEST_DELAY = 1.5


class WhiteHouseSpeechesScraper(BaseScraper):
    name = "whitehouse_speeches"
    version = "0.1.0"

    def __init__(
        self,
        session: Session,
        start_year: int = 2015,
        include_statements: bool = True,
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        self.include_statements = include_statements
        self.client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (academic research)"},
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        # whitehouse.gov is JavaScript-rendered (React/Next.js) and its WP REST API
        # returns 403. USE collectors/federal_register.py INSTEAD — it pulls the full
        # text of all presidential documents (executive orders, proclamations,
        # memoranda) from the open Federal Register API with no auth and no blocking:
        #   python -m sentiment_signal.collectors.federal_register --start-year 2015
        # Presidential speeches/remarks (as opposed to formal documents) require the
        # GovInfo DCPD collection (free api.data.gov key) or Playwright.
        logger.warning(
            "whitehouse_speeches: superseded by collectors/federal_register.py "
            "(open API, full text). Run that instead. Skipping."
        )
        return []

        items: list[RawItem] = []
        feeds = [("speech", WP_SPEECHES_API)]
        if self.include_statements:
            feeds.append(("statement", WP_STATEMENTS_API))

        for feed_type, api_url in feeds:
            items.extend(self._scrape_api(api_url, feed_type))

        return items

    def _scrape_api(self, api_template: str, feed_type: str) -> list[RawItem]:
        """Scrape via WordPress REST API (returns JSON)."""
        items: list[RawItem] = []
        page = 1

        while True:
            url = api_template.format(page=page)
            logger.info(f"whitehouse: {feed_type} page {page}")
            try:
                resp = self.client.get(url)
                if resp.status_code == 400:
                    # WP returns 400 when page exceeds total pages
                    break
                resp.raise_for_status()
                posts = resp.json()
            except Exception as exc:
                logger.warning(f"whitehouse: API failed page {page}: {exc}")
                break

            if not posts:
                break

            cutoff_hit = False
            for post in posts:
                date = _parse_wp_date(post.get("date", ""))
                if not date:
                    continue
                if date.year < self.start_year:
                    cutoff_hit = True
                    break

                link = post.get("link", "")
                existing = self.session.scalar(select(Statement).where(Statement.url == link))
                if existing:
                    continue

                # Extract plain text from rendered content
                rendered = post.get("content", {}).get("rendered", "")
                text = _strip_html(rendered)
                if not text or len(text) < 150:
                    continue

                title = _strip_html(post.get("title", {}).get("rendered", ""))
                # Speaker is often in the title: "Remarks by President Biden on..."
                speaker = _extract_speaker_from_title(title)

                items.append(
                    RawItem(
                        raw_text=text,
                        url=link,
                        published_at=date,
                        source_type=feed_type,
                        person_name=speaker,
                        platform="whitehouse.gov",
                        metadata={
                            "title": title,
                            "statement_subtype": f"whitehouse_{feed_type}",
                        },
                    )
                )

            if cutoff_hit:
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        return items

    def _persist(self, items: list[RawItem]) -> int:
        persons = self._load_persons()
        inserted = 0
        for item in items:
            person = resolve_person(item.person_name or "", persons)
            if person is None:
                logger.debug(f"whitehouse: no person match for '{item.person_name}', skipping")
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


def _extract_speaker_from_title(title: str) -> str:
    """Extract speaker name from WH title patterns.

    Examples:
      'Remarks by President Biden on the Economy'     -> 'Joe Biden'
      'Statement from President Trump on Ukraine'     -> 'Donald Trump'
      'Press Briefing by Press Secretary Karine Jean-Pierre' -> 'Karine Jean-Pierre'
    """
    patterns = [
        (r"(?i)president\s+biden", "Joe Biden"),
        (r"(?i)president\s+trump", "Donald Trump"),
        (r"(?i)vice\s+president\s+harris", "Kamala Harris"),
        (r"(?i)secretary\s+blinken", "Antony Blinken"),
        (r"(?i)secretary\s+rubio", "Marco Rubio"),
        (r"(?i)secretary\s+yellen", "Janet Yellen"),
        (r"(?i)secretary\s+austin", "Lloyd Austin"),
        (r"(?i)secretary\s+hegseth", "Pete Hegseth"),
    ]
    for pattern, name in patterns:
        if re.search(pattern, title):
            return name
    # Generic fallback: extract text after "by" or "from"
    m = re.search(r"(?i)(?:by|from)\s+([A-Z][a-zA-Z\s\-]{3,40}?)(?:\s+on|\s+at|\s+to|$)", title)
    return m.group(1).strip() if m else ""


def _parse_wp_date(s: str) -> datetime | None:
    # WordPress ISO format: "2024-01-15T10:30:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape White House speeches and statements")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--no-statements", action="store_true")
    args = parser.parse_args()

    session = SessionLocal()
    scraper = WhiteHouseSpeechesScraper(
        session,
        start_year=args.start_year,
        include_statements=not args.no_statements,
    )
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
