#!/usr/bin/env python3
"""Seed foreign central bankers so the BIS speeches feed stops skipping them.

The BIS RSS feed (collectors/bis_speeches.py) aggregates ECB, BoJ, Bundesbank,
SNB, PBoC, etc. speeches in English, but its _persist step drops any speaker not
already in `persons`. The seeded market-relevant corpus was ~98% US + Australia
(ECB=1, BoJ/Bundesbank/PBoC=0) while events span 16 global markets — so foreign
central bankers for ^N225, ^GDAXI, ^FCHI, ^HSI, ^KS11, EURUSD, etc. were missing.

Tiering rule: heads of *independent-policy* central banks (BoJ, PBoC, BoK, SNB)
and the ECB's primary rate communicators (President already seeded; Chief
Economist) are tier 1; euro-area national governors (one Governing Council voice,
not the rate-setter) and other executive-board / deputy members are tier 2.

Run after seed_persons.py and seed_geopolitical_persons.py:
    python scripts/seed_foreign_central_bankers.py
"""

import sys

sys.path.insert(0, ".")

from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.db.models import Person
from sentiment_signal.db.session import SessionLocal

# fmt: off
PERSONS = [
    # ── European Central Bank (Executive Board; Lagarde already seeded) ────────
    {
        "canonical_name": "Philip Lane",
        "aliases": ["Philip R. Lane", "Lane", "Philip R Lane"],
        "role": "Chief Economist & Member of the Executive Board", "institution": "European Central Bank",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Isabel Schnabel",
        "aliases": ["Schnabel"],
        "role": "Member of the Executive Board", "institution": "European Central Bank",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Luis de Guindos",
        "aliases": ["de Guindos", "Guindos"],
        "role": "Vice-President", "institution": "European Central Bank",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Piero Cipollone",
        "aliases": ["Cipollone"],
        "role": "Member of the Executive Board", "institution": "European Central Bank",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Frank Elderson",
        "aliases": ["Elderson"],
        "role": "Member of the Executive Board", "institution": "European Central Bank",
        "influence_tier": 2,
    },

    # ── Euro-area national central banks (Governing Council members) ───────────
    {
        "canonical_name": "Joachim Nagel",
        "aliases": ["Nagel", "Bundesbank President Nagel"],
        "role": "President", "institution": "Deutsche Bundesbank",
        "influence_tier": 2,
    },
    {
        "canonical_name": "François Villeroy de Galhau",
        "aliases": ["Francois Villeroy de Galhau", "Villeroy de Galhau", "Villeroy"],
        "role": "Governor", "institution": "Banque de France",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Fabio Panetta",
        "aliases": ["Panetta"],
        "role": "Governor", "institution": "Banca d'Italia",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Klaas Knot",
        "aliases": ["Knot"],
        "role": "President", "institution": "De Nederlandsche Bank",
        "influence_tier": 2,
    },

    # ── Bank of Japan (^N225, JPY) ────────────────────────────────────────────
    {
        "canonical_name": "Kazuo Ueda",
        "aliases": ["Ueda", "Governor Ueda"],
        "role": "Governor", "institution": "Bank of Japan",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Shinichi Uchida",
        "aliases": ["Uchida"],
        "role": "Deputy Governor", "institution": "Bank of Japan",
        "influence_tier": 2,
    },
    {
        "canonical_name": "Ryozo Himino",
        "aliases": ["Himino"],
        "role": "Deputy Governor", "institution": "Bank of Japan",
        "influence_tier": 2,
    },

    # ── Swiss National Bank (CHF safe-haven) ──────────────────────────────────
    {
        "canonical_name": "Martin Schlegel",
        "aliases": ["Schlegel"],
        "role": "Chairman", "institution": "Swiss National Bank",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Thomas Jordan",
        "aliases": ["Jordan", "SNB Chairman Jordan"],
        "role": "Chairman (2012-2024)", "institution": "Swiss National Bank",
        "influence_tier": 1, "is_active": False,
    },

    # ── People's Bank of China (^HSI, 000001.SS, CNY) ─────────────────────────
    {
        "canonical_name": "Pan Gongsheng",
        "aliases": ["Pan Gongsheng", "Governor Pan"],
        "role": "Governor", "institution": "People's Bank of China",
        "influence_tier": 1,
    },

    # ── Bank of Korea (^KS11) ─────────────────────────────────────────────────
    {
        "canonical_name": "Rhee Chang-yong",
        "aliases": ["Rhee Chang-yong", "Chang-yong Rhee", "Changyong Rhee", "Rhee"],
        "role": "Governor", "institution": "Bank of Korea",
        "influence_tier": 1,
    },
]
# fmt: on


def main() -> None:
    session = SessionLocal()
    try:
        inserted = skipped = 0
        for data in PERSONS:
            result = session.execute(
                insert(Person)
                .values(**data)
                .on_conflict_do_nothing(index_elements=["canonical_name"])
            )
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
