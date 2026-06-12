#!/usr/bin/env python3
"""Seed geopolitical figures, international-forum leaders, and war-context speakers.

Run after seed_persons.py (which covers central banks and tech CEOs):
    python scripts/seed_geopolitical_persons.py
"""

import sys

sys.path.insert(0, ".")

from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.db.models import Person
from sentiment_signal.db.session import SessionLocal

# fmt: off
PERSONS = [
    # ── NATO ─────────────────────────────────────────────────────────────────
    {
        "canonical_name": "Jens Stoltenberg",
        "aliases": ["Stoltenberg", "NATO Secretary General Stoltenberg"],
        "role": "Secretary General (2014-2024)", "institution": "NATO",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Mark Rutte",
        "aliases": ["Rutte", "NATO Secretary General Rutte"],
        "role": "Secretary General", "institution": "NATO",
        "influence_tier": 1,
    },

    # ── United Nations ────────────────────────────────────────────────────────
    {
        "canonical_name": "Antonio Guterres",
        "aliases": ["Guterres", "UN Secretary-General Guterres", "Secretary-General Guterres"],
        "role": "Secretary-General", "institution": "United Nations",
        "influence_tier": 1,
    },

    # ── IMF ───────────────────────────────────────────────────────────────────
    {
        "canonical_name": "Kristalina Georgieva",
        "aliases": ["Georgieva", "IMF Managing Director Georgieva"],
        "role": "Managing Director", "institution": "International Monetary Fund",
        "influence_tier": 1,
    },
    # Christine Lagarde served as IMF MD before ECB — already in central bank seed as ECB President
    # Adding alias linkage via a separate entry would cause canonical_name conflict; handled in resolve_person.

    # ── World Bank ────────────────────────────────────────────────────────────
    {
        "canonical_name": "Ajay Banga",
        "aliases": ["Banga", "World Bank President Banga"],
        "role": "President", "institution": "World Bank",
        "influence_tier": 1,
    },
    {
        "canonical_name": "David Malpass",
        "aliases": ["Malpass", "World Bank President Malpass"],
        "role": "President (2019-2023)", "institution": "World Bank",
        "influence_tier": 1, "is_active": False,
    },

    # ── WEF ───────────────────────────────────────────────────────────────────
    {
        "canonical_name": "Klaus Schwab",
        "aliases": ["Schwab", "WEF founder Schwab"],
        "role": "Founder and Executive Chairman", "institution": "World Economic Forum",
        "influence_tier": 2,
    },

    # ── European heads of government ──────────────────────────────────────────
    {
        "canonical_name": "Emmanuel Macron",
        "aliases": ["Macron", "President Macron"],
        "role": "President", "institution": "France",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Olaf Scholz",
        "aliases": ["Scholz", "Chancellor Scholz"],
        "role": "Chancellor", "institution": "Germany",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Angela Merkel",
        "aliases": ["Merkel", "Chancellor Merkel"],
        "role": "Chancellor (2005-2021)", "institution": "Germany",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Keir Starmer",
        "aliases": ["Starmer", "Prime Minister Starmer", "PM Starmer"],
        "role": "Prime Minister", "institution": "United Kingdom",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Rishi Sunak",
        "aliases": ["Sunak", "Prime Minister Sunak", "PM Sunak"],
        "role": "Prime Minister (2022-2024)", "institution": "United Kingdom",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Boris Johnson",
        "aliases": ["Boris Johnson", "Prime Minister Johnson", "Boris"],
        "role": "Prime Minister (2019-2022)", "institution": "United Kingdom",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Theresa May",
        "aliases": ["May", "Prime Minister May"],
        "role": "Prime Minister (2016-2019)", "institution": "United Kingdom",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Charles Michel",
        "aliases": ["Michel", "Council President Michel"],
        "role": "President", "institution": "European Council",
        "influence_tier": 2,
    },

    # ── US heads of state (for Federal Register presidential documents) ───────
    {
        "canonical_name": "Barack Obama",
        "aliases": ["Obama", "President Obama"],
        "role": "President (2009-2017)", "institution": "United States",
        "influence_tier": 1, "is_active": False,
    },

    # ── Conflict-specific figures ─────────────────────────────────────────────
    {
        "canonical_name": "Volodymyr Zelensky",
        "aliases": ["Zelensky", "President Zelensky", "Zelenskyy"],
        "role": "President", "institution": "Ukraine",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Benjamin Netanyahu",
        "aliases": ["Netanyahu", "Prime Minister Netanyahu", "PM Netanyahu", "Bibi"],
        "role": "Prime Minister", "institution": "Israel",
        "influence_tier": 1,
    },

    # ── US foreign and defence policy ─────────────────────────────────────────
    {
        "canonical_name": "Antony Blinken",
        "aliases": ["Blinken", "Secretary Blinken", "Secretary of State Blinken"],
        "role": "Secretary of State (2021-2025)", "institution": "U.S. Department of State",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Marco Rubio",
        "aliases": ["Rubio", "Secretary Rubio", "Secretary of State Rubio"],
        "role": "Secretary of State", "institution": "U.S. Department of State",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Mike Pompeo",
        "aliases": ["Pompeo", "Secretary Pompeo"],
        "role": "Secretary of State (2018-2021)", "institution": "U.S. Department of State",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Rex Tillerson",
        "aliases": ["Tillerson", "Secretary Tillerson"],
        "role": "Secretary of State (2017-2018)", "institution": "U.S. Department of State",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Lloyd Austin",
        "aliases": ["Austin", "Secretary Austin", "Secretary of Defense Austin"],
        "role": "Secretary of Defense (2021-2025)", "institution": "U.S. Department of Defense",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Pete Hegseth",
        "aliases": ["Hegseth", "Secretary Hegseth", "Secretary of Defense Hegseth"],
        "role": "Secretary of Defense", "institution": "U.S. Department of Defense",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Mark Milley",
        "aliases": ["Milley", "General Milley", "Chairman Milley"],
        "role": "Chairman, Joint Chiefs of Staff (2019-2023)", "institution": "U.S. Department of Defense",
        "influence_tier": 2, "is_active": False,
    },

    # ── Asia-Pacific heads of government ─────────────────────────────────────
    {
        "canonical_name": "Fumio Kishida",
        "aliases": ["Kishida", "Prime Minister Kishida"],
        "role": "Prime Minister (2021-2024)", "institution": "Japan",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Shigeru Ishiba",
        "aliases": ["Ishiba", "Prime Minister Ishiba"],
        "role": "Prime Minister", "institution": "Japan",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Anthony Albanese",
        "aliases": ["Albanese", "Prime Minister Albanese"],
        "role": "Prime Minister", "institution": "Australia",
        "influence_tier": 2,
    },

    # ── International economic institutions ───────────────────────────────────
    {
        "canonical_name": "Mathias Cormann",
        "aliases": ["Cormann", "OECD Secretary-General Cormann"],
        "role": "Secretary-General", "institution": "OECD",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Ngozi Okonjo-Iweala",
        "aliases": ["Okonjo-Iweala", "WTO Director-General"],
        "role": "Director-General", "institution": "World Trade Organization",
        "influence_tier": 2,
    },
]
# fmt: on


def main() -> None:
    session = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for data in PERSONS:
            stmt = (
                insert(Person)
                .values(**data)
                .on_conflict_do_nothing(index_elements=["canonical_name"])
            )
            result = session.execute(stmt)
            if result.rowcount:
                inserted += 1
            else:
                skipped += 1
        session.commit()
        print(f"Done: {inserted} inserted, {skipped} already existed.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
