"""Scraper for US presidential documents via the Federal Register API.

Source: https://www.federalregister.gov/api/v1/documents.json
This is a first-class open JSON API (no auth, no Cloudflare) that serves the full
text of every presidential document: executive orders, proclamations, memoranda,
and determinations. These carry strong market signals — sanctions EOs, tariff
proclamations, national emergency declarations, trade actions.

This replaces direct scraping of whitehouse.gov, which is JavaScript-rendered and
blocks its own REST API.

Coverage: Obama, Trump, Biden (the persons table must contain matching entries).

Usage:
    python -m sentiment_signal.collectors.federal_register --start-year 2015
    python -m sentiment_signal.collectors.federal_register --start-year 2022 --doc-types "Executive Order" Proclamation
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
from sentiment_signal.utils.terminal import progress

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
REQUEST_DELAY = 0.5  # API is generous; raw-text fetches use the same delay

# Fields the API must return (sent as repeated fields[]= params — httpx list
# encoding is rejected by the API, so the query string is built manually).
_FIELDS = [
    "title",
    "publication_date",
    "signing_date",
    "president",
    "document_number",
    "raw_text_url",
    "html_url",
    "subtype",
]

# Map Federal Register president identifiers to canonical_name in the persons table.
# resolve_person cannot match "Joseph R. Biden Jr." to "Joe Biden" reliably, so we
# translate the stable identifier instead.
_PRESIDENT_MAP = {
    "joe-biden": "Joe Biden",
    "donald-trump": "Donald Trump",
    "barack-obama": "Barack Obama",
}

# FR raw text is prefixed with a boilerplate header inside square brackets plus a
# GPO notice. This pattern strips everything up to and including that notice.
_BOILERPLATE_RE = re.compile(
    r"^.*?Government Publishing Office\s*\[www\.gpo\.gov\]\s*(\[FR Doc[^\]]*\])?",
    re.IGNORECASE,
)


class FederalRegisterScraper(BaseScraper):
    name = "federal_register"
    version = "0.1.0"

    def __init__(
        self,
        session: Session,
        start_year: int = 2015,
        doc_types: list[str] | None = None,
    ) -> None:
        super().__init__(session)
        self.start_year = start_year
        # Optional filter on subtype, e.g. ["Executive Order", "Proclamation"]
        self.doc_types = set(doc_types) if doc_types else None
        self.client = httpx.Client(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
            timeout=30,
            follow_redirects=True,
        )
        self._person_cache: list[Person] | None = None

    def collect(self) -> list[RawItem]:
        items: list[RawItem] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            url = self._build_query(page)
            try:
                resp = self.client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(f"federal_register: listing page {page} failed: {exc}")
                break

            total_pages = min(data.get("total_pages", 1), 50)  # API caps at 2000 results
            results = data.get("results", [])
            if not results:
                break
            logger.info(
                f"federal_register: page {page}/{total_pages}, "
                f"{len(results)} docs ({data.get('count')} total)"
            )

            for doc in progress(results, f"federal_register page {page} docs", every=25):
                subtype = doc.get("subtype") or "presidential_document"
                if self.doc_types and subtype not in self.doc_types:
                    continue

                url_ = doc.get("html_url", "")
                existing = self.session.scalar(select(Statement).where(Statement.url == url_))
                if existing:
                    continue

                raw_text_url = doc.get("raw_text_url")
                if not raw_text_url:
                    continue

                time.sleep(REQUEST_DELAY)
                text = self._fetch_raw_text(raw_text_url)
                if not text or len(text) < 150:
                    continue

                # signing_date is when the president signed; publication_date is when
                # the FR published it. Signing is the market-relevant timestamp.
                date = _parse_date(doc.get("signing_date") or doc.get("publication_date"))
                if not date or date.year < self.start_year:
                    continue

                pres = doc.get("president") or {}
                speaker = _PRESIDENT_MAP.get(pres.get("identifier", ""), pres.get("name", ""))

                items.append(
                    RawItem(
                        raw_text=text,
                        url=url_,
                        published_at=date,
                        source_type="presidential_document",
                        person_name=speaker,
                        platform="federalregister.gov",
                        metadata={
                            "title": doc.get("title", ""),
                            "statement_subtype": _normalise_subtype(subtype),
                        },
                    )
                )

            page += 1
            time.sleep(REQUEST_DELAY)

        logger.info(f"federal_register: {len(items)} documents collected")
        return items

    def _build_query(self, page: int) -> str:
        parts = [
            f"{API_URL}?conditions[type][]=PRESDOCU",
            f"&conditions[publication_date][gte]={self.start_year}-01-01",
            "".join(f"&fields[]={f}" for f in _FIELDS),
            f"&per_page=100&page={page}&order=oldest",
        ]
        return "".join(parts)

    def _fetch_raw_text(self, raw_text_url: str) -> str:
        try:
            resp = self.client.get(raw_text_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug(f"federal_register: raw text fetch failed {raw_text_url}: {exc}")
            return ""
        pre = BeautifulSoup(resp.text, "html.parser").find("pre")
        text = pre.get_text() if pre else ""
        text = " ".join(text.split())
        # Strip the FR/GPO boilerplate header so FinBERT scores the actual content
        text = _BOILERPLATE_RE.sub("", text, count=1).strip()
        # Strip NUL/control chars — some FR documents embed them and PostgreSQL rejects NUL
        return self.clean_text(text)

    def _persist(self, items: list[RawItem]) -> int:
        persons = self._load_persons()
        inserted = 0
        pending = 0
        for item in items:
            person = resolve_person(item.person_name or "", persons)
            if person is None:
                logger.debug(
                    f"federal_register: no person match for '{item.person_name}', skipping"
                )
                continue

            content_hash = self.content_hash(item.raw_text)
            try:
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
            except Exception as exc:
                # Don't let one bad row abort the whole batch
                self.session.rollback()
                logger.warning(f"federal_register: skipped a row ({item.url}): {exc}")
                continue
            if result.rowcount:
                inserted += 1
            pending += 1
            # Commit in batches so a late failure cannot discard the whole run
            if pending >= 100:
                self.session.commit()
                pending = 0
        self.session.commit()
        return inserted

    def _load_persons(self) -> list[Person]:
        if self._person_cache is None:
            self._person_cache = self.session.scalars(select(Person)).all()
        return list(self._person_cache)


def _normalise_subtype(subtype: str) -> str:
    """Map FR subtype to a compact statement_subtype value (max 50 chars)."""
    return "fr_" + re.sub(r"[^a-z0-9]+", "_", subtype.lower()).strip("_")[:46]


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape US presidential documents via Federal Register API"
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument(
        "--doc-types",
        nargs="+",
        default=None,
        help='Filter by subtype, e.g. "Executive Order" Proclamation Memorandum',
    )
    args = parser.parse_args()

    session = SessionLocal()
    scraper = FederalRegisterScraper(session, start_year=args.start_year, doc_types=args.doc_types)
    total = scraper.run()
    print(f"Inserted {total} new statements.")
    session.close()
