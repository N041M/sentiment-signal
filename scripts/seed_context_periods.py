#!/usr/bin/env python3
"""Seed the context_periods table with curated high-impact events / regimes.

A macro-context overlay (pandemics, wars, policy regimes, crises) used to stratify
analysis by regime. Dates are from public record; source_url cites an authoritative
domain. end_date=None means ongoing.

Coverage: 2015 to mid-2025 (the reliable horizon at authoring time). Add later-2025
and 2026 events as they become known — the corpus extends to 2026.

    python scripts/seed_context_periods.py
"""

import sys
from datetime import UTC, datetime

sys.path.insert(0, ".")

from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.db.models import ContextPeriod
from sentiment_signal.db.session import SessionLocal


def d(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


# fmt: off
PERIODS = [
    # ── Pandemics ─────────────────────────────────────────────────────────────
    {"name": "COVID-19 pandemic", "category": "pandemic",
     "start_date": d(2020, 1, 30), "end_date": d(2023, 5, 5), "onset_date": d(2020, 3, 11),
     "impact_tier": 1, "geography": "global",
     "description": "WHO PHEIC 2020-01-30; pandemic declared 2020-03-11; PHEIC ended 2023-05-05.",
     "source_url": "https://www.who.int"},

    # ── Wars & conflict ───────────────────────────────────────────────────────
    {"name": "Russia–Ukraine war", "category": "war_conflict",
     "start_date": d(2022, 2, 24), "end_date": None, "onset_date": d(2022, 2, 24),
     "impact_tier": 1, "geography": "global",
     "description": "Full-scale invasion; energy/commodity shock, sanctions regime.",
     "source_url": "https://www.un.org"},
    {"name": "Israel–Hamas war", "category": "war_conflict",
     "start_date": d(2023, 10, 7), "end_date": None, "onset_date": d(2023, 10, 7),
     "impact_tier": 2, "geography": "middle_east",
     "description": "Oct 7 attack and ensuing war; regional escalation risk.",
     "source_url": "https://www.un.org"},
    {"name": "Red Sea shipping crisis", "category": "war_conflict",
     "start_date": d(2023, 11, 19), "end_date": None, "onset_date": d(2023, 11, 19),
     "impact_tier": 3, "geography": "global",
     "description": "Houthi attacks disrupt Suez/Red Sea shipping; freight costs spike.",
     "source_url": "https://www.un.org"},
    {"name": "Soleimani strike / US–Iran tensions", "category": "war_conflict",
     "start_date": d(2020, 1, 3), "end_date": d(2020, 1, 31), "onset_date": d(2020, 1, 3),
     "impact_tier": 3, "geography": "middle_east",
     "description": "US strike kills Soleimani; brief oil/risk spike.",
     "source_url": "https://www.un.org"},
    {"name": "Fall of Kabul / Afghanistan withdrawal", "category": "war_conflict",
     "start_date": d(2021, 8, 15), "end_date": d(2021, 8, 31), "onset_date": d(2021, 8, 15),
     "impact_tier": 3, "geography": "global",
     "description": "Taliban take Kabul during US withdrawal.",
     "source_url": "https://www.un.org"},

    # ── Monetary policy ───────────────────────────────────────────────────────
    {"name": "Fed liftoff (first hike post-GFC)", "category": "monetary_policy",
     "start_date": d(2015, 12, 16), "end_date": d(2018, 12, 19), "onset_date": d(2015, 12, 16),
     "impact_tier": 2, "geography": "US",
     "description": "Gradual tightening cycle 2015–2018.",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "Fed balance-sheet normalization (QT1)", "category": "monetary_policy",
     "start_date": d(2017, 10, 1), "end_date": d(2019, 8, 1), "onset_date": d(2017, 10, 1),
     "impact_tier": 3, "geography": "US",
     "description": "First quantitative tightening programme.",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "Fed mid-cycle cuts 2019", "category": "monetary_policy",
     "start_date": d(2019, 7, 31), "end_date": d(2019, 10, 30), "onset_date": d(2019, 7, 31),
     "impact_tier": 3, "geography": "US",
     "description": "Three insurance cuts amid trade-war slowdown.",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "Fed COVID emergency easing + QE", "category": "monetary_policy",
     "start_date": d(2020, 3, 15), "end_date": d(2022, 3, 16), "onset_date": d(2020, 3, 15),
     "impact_tier": 1, "geography": "US",
     "description": "Rates cut to zero, unlimited QE; ultra-accommodative regime.",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "Fed hiking cycle 2022–2023", "category": "monetary_policy",
     "start_date": d(2022, 3, 16), "end_date": d(2023, 7, 26), "onset_date": d(2022, 3, 16),
     "impact_tier": 1, "geography": "US",
     "description": "Fastest tightening in decades (to ~5.25–5.5%).",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "Fed pivot to cuts 2024", "category": "monetary_policy",
     "start_date": d(2024, 9, 18), "end_date": None, "onset_date": d(2024, 9, 18),
     "impact_tier": 2, "geography": "US",
     "description": "First cut of the easing cycle (50bp).",
     "source_url": "https://www.federalreserve.gov/monetarypolicy.htm"},
    {"name": "ECB asset purchase programme (QE)", "category": "monetary_policy",
     "start_date": d(2015, 3, 9), "end_date": d(2018, 12, 31), "onset_date": d(2015, 3, 9),
     "impact_tier": 2, "geography": "EU",
     "description": "Expanded APP / public-sector purchases begin.",
     "source_url": "https://www.ecb.europa.eu"},
    {"name": "ECB hiking cycle 2022–2023", "category": "monetary_policy",
     "start_date": d(2022, 7, 21), "end_date": d(2023, 9, 20), "onset_date": d(2022, 7, 21),
     "impact_tier": 2, "geography": "EU",
     "description": "ECB exits negative rates and tightens.",
     "source_url": "https://www.ecb.europa.eu"},
    {"name": "BoJ negative rates / YCC", "category": "monetary_policy",
     "start_date": d(2016, 1, 29), "end_date": d(2024, 3, 19), "onset_date": d(2016, 1, 29),
     "impact_tier": 2, "geography": "JP",
     "description": "NIRP (2016) and yield-curve control until the 2024 exit.",
     "source_url": "https://www.boj.or.jp/en"},
    {"name": "BoE hiking cycle 2021–2023", "category": "monetary_policy",
     "start_date": d(2021, 12, 16), "end_date": d(2023, 8, 3), "onset_date": d(2021, 12, 16),
     "impact_tier": 3, "geography": "UK",
     "description": "BoE tightens against inflation.",
     "source_url": "https://www.bankofengland.co.uk"},

    # ── Fiscal & trade ────────────────────────────────────────────────────────
    {"name": "US tax cuts (TCJA)", "category": "fiscal_trade",
     "start_date": d(2017, 12, 22), "end_date": None, "onset_date": d(2017, 12, 22),
     "impact_tier": 2, "geography": "US",
     "description": "Tax Cuts and Jobs Act signed.",
     "source_url": "https://www.congress.gov"},
    {"name": "US–China trade war (2018–2019)", "category": "fiscal_trade",
     "start_date": d(2018, 3, 22), "end_date": d(2020, 1, 15), "onset_date": d(2018, 7, 6),
     "impact_tier": 1, "geography": "global",
     "description": "Section 301 tariffs; first tariffs effective 2018-07-06; Phase One 2020-01-15.",
     "source_url": "https://ustr.gov"},
    {"name": "Section 232 steel & aluminum tariffs", "category": "fiscal_trade",
     "start_date": d(2018, 3, 8), "end_date": None, "onset_date": d(2018, 3, 8),
     "impact_tier": 2, "geography": "global",
     "description": "Steel/aluminum tariff proclamations.",
     "source_url": "https://www.federalregister.gov"},
    {"name": "CARES Act stimulus", "category": "fiscal_trade",
     "start_date": d(2020, 3, 27), "end_date": None, "onset_date": d(2020, 3, 27),
     "impact_tier": 1, "geography": "US",
     "description": "$2.2T COVID relief package.",
     "source_url": "https://www.congress.gov"},
    {"name": "American Rescue Plan", "category": "fiscal_trade",
     "start_date": d(2021, 3, 11), "end_date": None, "onset_date": d(2021, 3, 11),
     "impact_tier": 2, "geography": "US",
     "description": "$1.9T stimulus; contributed to 2021–22 inflation debate.",
     "source_url": "https://www.congress.gov"},
    {"name": "Inflation Reduction Act", "category": "fiscal_trade",
     "start_date": d(2022, 8, 16), "end_date": None, "onset_date": d(2022, 8, 16),
     "impact_tier": 2, "geography": "US",
     "description": "Climate/health/tax package.",
     "source_url": "https://www.congress.gov"},
    {"name": "2025 US tariff regime", "category": "fiscal_trade",
     "start_date": d(2025, 4, 2), "end_date": None, "onset_date": d(2025, 4, 2),
     "impact_tier": 1, "geography": "global",
     "description": "Broad 2025 reciprocal/'Liberation Day' tariffs; major trade-policy shift.",
     "source_url": "https://www.federalregister.gov"},

    # ── Financial crises & stress ─────────────────────────────────────────────
    {"name": "Greek debt crisis 2015", "category": "financial_crisis",
     "start_date": d(2015, 6, 1), "end_date": d(2015, 8, 20), "onset_date": d(2015, 7, 5),
     "impact_tier": 3, "geography": "EU",
     "description": "Bailout referendum 2015-07-05; Grexit fears.",
     "source_url": "https://www.ecb.europa.eu"},
    {"name": "COVID market crash", "category": "financial_crisis",
     "start_date": d(2020, 2, 20), "end_date": d(2020, 4, 7), "onset_date": d(2020, 3, 16),
     "impact_tier": 1, "geography": "global",
     "description": "Fastest bear market on record; circuit breakers.",
     "source_url": "https://www.federalreserve.gov"},
    {"name": "UK gilt / LDI crisis", "category": "financial_crisis",
     "start_date": d(2022, 9, 23), "end_date": d(2022, 10, 17), "onset_date": d(2022, 9, 23),
     "impact_tier": 2, "geography": "UK",
     "description": "Mini-budget triggers gilt rout; BoE emergency intervention.",
     "source_url": "https://www.bankofengland.co.uk"},
    {"name": "US regional banking crisis (SVB)", "category": "financial_crisis",
     "start_date": d(2023, 3, 10), "end_date": d(2023, 5, 1), "onset_date": d(2023, 3, 10),
     "impact_tier": 1, "geography": "US",
     "description": "SVB and Signature fail; First Republic 2023-05-01.",
     "source_url": "https://www.federalreserve.gov"},
    {"name": "Credit Suisse collapse / UBS takeover", "category": "financial_crisis",
     "start_date": d(2023, 3, 19), "end_date": d(2023, 3, 19), "onset_date": d(2023, 3, 19),
     "impact_tier": 2, "geography": "EU",
     "description": "Emergency UBS acquisition of Credit Suisse.",
     "source_url": "https://www.snb.ch"},
    {"name": "US debt-ceiling crisis 2023", "category": "financial_crisis",
     "start_date": d(2023, 1, 19), "end_date": d(2023, 6, 3), "onset_date": d(2023, 6, 3),
     "impact_tier": 3, "geography": "US",
     "description": "Standoff resolved 2023-06-03; Fitch downgrade 2023-08-01.",
     "source_url": "https://home.treasury.gov"},
    {"name": "Evergrande / China property crisis", "category": "financial_crisis",
     "start_date": d(2021, 9, 1), "end_date": None, "onset_date": d(2021, 9, 23),
     "impact_tier": 2, "geography": "CN",
     "description": "Evergrande liquidity crisis; broader property-sector stress.",
     "source_url": "https://www.imf.org"},
    {"name": "FTX collapse", "category": "financial_crisis",
     "start_date": d(2022, 11, 11), "end_date": d(2022, 11, 30), "onset_date": d(2022, 11, 11),
     "impact_tier": 3, "geography": "global",
     "description": "Crypto exchange bankruptcy; contagion across digital assets.",
     "source_url": "https://www.sec.gov"},

    # ── Political & sovereign ─────────────────────────────────────────────────
    {"name": "Brexit referendum & process", "category": "political",
     "start_date": d(2016, 6, 23), "end_date": d(2020, 1, 31), "onset_date": d(2016, 6, 23),
     "impact_tier": 1, "geography": "UK",
     "description": "Leave vote 2016-06-23; UK exits EU 2020-01-31.",
     "source_url": "https://www.gov.uk"},
    {"name": "US 2016 election", "category": "political",
     "start_date": d(2016, 11, 8), "end_date": d(2017, 1, 20), "onset_date": d(2016, 11, 8),
     "impact_tier": 2, "geography": "US",
     "description": "Trump elected; policy-regime shift.",
     "source_url": "https://www.archives.gov"},
    {"name": "US 2020 election & transition", "category": "political",
     "start_date": d(2020, 11, 3), "end_date": d(2021, 1, 20), "onset_date": d(2021, 1, 6),
     "impact_tier": 2, "geography": "US",
     "description": "Biden elected; Jan 6 2021-01-06; transition.",
     "source_url": "https://www.archives.gov"},
    {"name": "US 2024 election & transition", "category": "political",
     "start_date": d(2024, 11, 5), "end_date": d(2025, 1, 20), "onset_date": d(2024, 11, 5),
     "impact_tier": 2, "geography": "US",
     "description": "Trump re-elected; policy-regime shift into 2025.",
     "source_url": "https://www.archives.gov"},

    # ── Energy & commodities ──────────────────────────────────────────────────
    {"name": "Negative WTI oil price", "category": "energy",
     "start_date": d(2020, 4, 20), "end_date": d(2020, 4, 21), "onset_date": d(2020, 4, 20),
     "impact_tier": 3, "geography": "global",
     "description": "WTI May contract settles negative amid demand collapse.",
     "source_url": "https://www.eia.gov"},
    {"name": "European energy crisis 2021–2022", "category": "energy",
     "start_date": d(2021, 9, 1), "end_date": d(2023, 3, 31), "onset_date": d(2022, 2, 24),
     "impact_tier": 2, "geography": "EU",
     "description": "Gas price surge, worsened by the Ukraine war.",
     "source_url": "https://www.iea.org"},

    # ── Technology ────────────────────────────────────────────────────────────
    {"name": "Generative-AI boom (ChatGPT)", "category": "technology",
     "start_date": d(2022, 11, 30), "end_date": None, "onset_date": d(2022, 11, 30),
     "impact_tier": 2, "geography": "global",
     "description": "ChatGPT launch; AI capex/equity rally (Nvidia et al.).",
     "source_url": "https://openai.com"},
    {"name": "China zero-COVID exit / reopening", "category": "political",
     "start_date": d(2022, 12, 7), "end_date": d(2023, 2, 28), "onset_date": d(2022, 12, 7),
     "impact_tier": 3, "geography": "CN",
     "description": "Abrupt end of zero-COVID; reopening trade.",
     "source_url": "https://www.imf.org"},
]
# fmt: on


def main() -> None:
    session = SessionLocal()
    try:
        inserted = skipped = 0
        for data in PERIODS:
            result = session.execute(
                insert(ContextPeriod).values(**data).on_conflict_do_nothing(index_elements=["name"])
            )
            if result.rowcount:
                inserted += 1
            else:
                skipped += 1
        session.commit()
        print(f"Done: {inserted} inserted, {skipped} already existed ({len(PERIODS)} total).")
    finally:
        session.close()


if __name__ == "__main__":
    main()
