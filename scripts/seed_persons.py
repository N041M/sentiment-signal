#!/usr/bin/env python3
"""Seed the persons table with ~40 influential figures.

Run from the project root with the venv active:
    python scripts/seed_persons.py
"""

import sys

sys.path.insert(0, ".")

from sqlalchemy.dialects.postgresql import insert

from sentiment_signal.db.models import Person
from sentiment_signal.db.session import SessionLocal

# fmt: off
PERSONS = [
    # ── Bank of England MPC members & senior officials ───────────────────────
    {
        "canonical_name": "Megan Greene",
        "aliases": ["Greene", "Megan Greene"],
        "role": "External MPC Member", "institution": "Bank of England", "influence_tier": 3,
    },
    {
        "canonical_name": "Sarah Breeden",
        "aliases": ["Breeden"],
        "role": "Deputy Governor, Financial Stability", "institution": "Bank of England", "influence_tier": 2,
    },
    {
        "canonical_name": "Huw Pill",
        "aliases": ["Pill"],
        "role": "Chief Economist", "institution": "Bank of England", "influence_tier": 2,
    },
    {
        "canonical_name": "Dave Ramsden",
        "aliases": ["Ramsden"],
        "role": "Deputy Governor, Markets & Banking", "institution": "Bank of England", "influence_tier": 2,
    },
    {
        "canonical_name": "Clare Lombardelli",
        "aliases": ["Lombardelli"],
        "role": "Deputy Governor, Monetary Policy", "institution": "Bank of England", "influence_tier": 2,
    },
    {
        "canonical_name": "Catherine Mann",
        "aliases": ["Mann"],
        "role": "External MPC Member", "institution": "Bank of England", "influence_tier": 3,
    },
    {
        "canonical_name": "Swati Dhingra",
        "aliases": ["Dhingra"],
        "role": "External MPC Member", "institution": "Bank of England", "influence_tier": 3,
    },
    {
        "canonical_name": "Ben Broadbent",
        "aliases": ["Broadbent"],
        "role": "Deputy Governor (2011–2024)", "institution": "Bank of England",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Jon Cunliffe",
        "aliases": ["Cunliffe"],
        "role": "Deputy Governor (2013–2023)", "institution": "Bank of England",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Victoria Cleland",
        "aliases": ["Cleland"],
        "role": "Executive Director, Payments", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "Lee Foulger",
        "aliases": ["Foulger"],
        "role": "Director, Financial Stability", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "Charlotte Gerken",
        "aliases": ["Gerken"],
        "role": "Director, Insurance Supervision", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "Jonathan Hall",
        "aliases": ["Hall", "Jonathan Hall"],
        "role": "FPC External Member", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "Sasha Mills",
        "aliases": ["Mills", "Sasha Mills"],
        "role": "Executive Director", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "James Talbot",
        "aliases": ["Talbot"],
        "role": "Senior Economist", "institution": "Bank of England", "influence_tier": 4,
    },
    {
        "canonical_name": "Laura Wallis",
        "aliases": ["Wallis"],
        "role": "Senior Official", "institution": "Bank of England", "influence_tier": 4,
    },

    # ── Reserve Bank of Australia ─────────────────────────────────────────────
    {
        "canonical_name": "Michele Bullock",
        "aliases": ["Bullock", "Governor Bullock"],
        "role": "Governor", "institution": "Reserve Bank of Australia", "influence_tier": 2,
    },
    {
        "canonical_name": "Philip Lowe",
        "aliases": ["Lowe", "Governor Lowe"],
        "role": "Governor (2016–2023)", "institution": "Reserve Bank of Australia",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Sarah Hunter",
        "aliases": ["Hunter"],
        "role": "Assistant Governor, Economics", "institution": "Reserve Bank of Australia", "influence_tier": 3,
    },
    {
        "canonical_name": "Christopher Kent",
        "aliases": ["Kent"],
        "role": "Assistant Governor, Financial Markets", "institution": "Reserve Bank of Australia", "influence_tier": 3,
    },
    {
        "canonical_name": "Brad Jones",
        "aliases": ["Brad Jones", "Bradley Jones"],
        "role": "Assistant Governor", "institution": "Reserve Bank of Australia", "influence_tier": 3,
    },
    {
        "canonical_name": "Glenn Stevens",
        "aliases": ["Stevens", "Governor Stevens", "Glenn Stevens AC"],
        "role": "Governor (2006–2016)", "institution": "Reserve Bank of Australia",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Malcolm Edey",
        "aliases": ["Edey"],
        "role": "Assistant Governor, Financial System (2007–2016)", "institution": "Reserve Bank of Australia",
        "influence_tier": 3, "is_active": False,
    },
    {
        "canonical_name": "Alexandra Heath",
        "aliases": ["Heath"],
        "role": "Head of International Department", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Guy Debelle",
        "aliases": ["Debelle"],
        "role": "Deputy Governor (2016–2022)", "institution": "Reserve Bank of Australia",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Andrew Hauser",
        "aliases": ["Hauser"],
        "role": "Deputy Governor", "institution": "Reserve Bank of Australia", "influence_tier": 2,
    },
    {
        "canonical_name": "Luci Ellis",
        "aliases": ["Ellis"],
        "role": "Assistant Governor, Economics (2012–2022)", "institution": "Reserve Bank of Australia",
        "influence_tier": 3, "is_active": False,
    },
    {
        "canonical_name": "Jonathan Kearns",
        "aliases": ["Kearns"],
        "role": "Head of Financial Stability (2014–2022)", "institution": "Reserve Bank of Australia",
        "influence_tier": 3, "is_active": False,
    },
    {
        "canonical_name": "Marion Kohler",
        "aliases": ["Kohler"],
        "role": "Head of Economic Research", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Jacqui Dwyer",
        "aliases": ["Dwyer"],
        "role": "Head of Financial Stability", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Ellis Connolly",
        "aliases": ["Connolly", "Ellis Connolly"],
        "role": "Head of Payments Policy", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Tony Richards",
        "aliases": ["Richards", "Tony Richards"],
        "role": "Head of Payments Policy (retired)", "institution": "Reserve Bank of Australia",
        "influence_tier": 4, "is_active": False,
    },
    {
        "canonical_name": "John Simon",
        "aliases": ["John Simon"],
        "role": "Head of Research", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "David Jacobs",
        "aliases": ["Jacobs"],
        "role": "Head of Domestic Markets", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Carl Schwartz",
        "aliases": ["Carl Schwartz"],
        "role": "Senior Manager, Payments", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Andrea Brischetto",
        "aliases": ["Brischetto"],
        "role": "Senior Economist", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Kim Nguyen",
        "aliases": ["Kim Nguyen"],
        "role": "Head of Payments Policy", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Penelope Smith",
        "aliases": ["Penelope Smith"],
        "role": "Head of International Economics", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Callan Windsor",
        "aliases": ["Windsor"],
        "role": "Head of Financial Stability", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Michael Plumb",
        "aliases": ["Plumb"],
        "role": "Senior Economist", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Gayan Benedict",
        "aliases": ["Benedict"],
        "role": "Senior Manager", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Matthew Boge",
        "aliases": ["Boge"],
        "role": "Head of Payments", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Chris Aylmer",
        "aliases": ["Aylmer"],
        "role": "Head of Domestic Markets", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Chris Ryan",
        "aliases": ["Chris Ryan"],
        "role": "Senior Economist", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Sarv Girn",
        "aliases": ["Girn"],
        "role": "Head of Information Technology", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Merylin Coombs",
        "aliases": ["Coombs"],
        "role": "Senior Manager", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },
    {
        "canonical_name": "Lindsay Boulton",
        "aliases": ["Boulton"],
        "role": "Senior Manager", "institution": "Reserve Bank of Australia", "influence_tier": 4,
    },

    # ── Bank of Canada ────────────────────────────────────────────────────────
    {
        "canonical_name": "Tiff Macklem",
        "aliases": ["Macklem", "Governor Macklem"],
        "role": "Governor", "institution": "Bank of Canada", "influence_tier": 2,
    },
    {
        "canonical_name": "Stephen Poloz",
        "aliases": ["Poloz", "Governor Poloz"],
        "role": "Governor (2013–2020)", "institution": "Bank of Canada",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Carolyn Rogers",
        "aliases": ["Rogers"],
        "role": "Senior Deputy Governor", "institution": "Bank of Canada", "influence_tier": 3,
    },

    # ── Tier 1: Central bank chairs — single statement can move global markets ──
    {
        "canonical_name": "Jerome Powell",
        "aliases": ["Jay Powell", "Fed Chair Powell", "Powell"],
        "role": "Chair", "institution": "Federal Reserve", "influence_tier": 1,
    },
    {
        "canonical_name": "Ben Bernanke",
        "aliases": ["Bernanke", "Fed Chair Bernanke"],
        "role": "Chair (2006–2014)", "institution": "Federal Reserve",
        "influence_tier": 1, "is_active": False,
    },
    {
        "canonical_name": "Janet Yellen",
        "aliases": ["Yellen", "Secretary Yellen", "Fed Chair Yellen"],
        "role": "Secretary of the Treasury", "institution": "U.S. Department of the Treasury",
        "influence_tier": 1,
    },
    {
        "canonical_name": "Christine Lagarde",
        "aliases": ["Lagarde", "ECB President Lagarde"],
        "role": "President", "institution": "European Central Bank", "influence_tier": 1,
    },
    {
        "canonical_name": "Andrew Bailey",
        "aliases": ["Bailey", "BoE Governor Bailey"],
        "role": "Governor", "institution": "Bank of England", "influence_tier": 1,
    },

    # ── Tier 2: Heads of state & senior Fed board members ────────────────────
    {
        "canonical_name": "Donald Trump",
        "aliases": ["Trump", "President Trump"],
        "role": "President", "institution": "United States", "influence_tier": 2,
    },
    {
        "canonical_name": "Joe Biden",
        "aliases": ["Biden", "President Biden"],
        "role": "President (2021–2025)", "institution": "United States", "influence_tier": 2,
    },
    {
        "canonical_name": "Xi Jinping",
        "aliases": ["Xi", "President Xi"],
        "role": "President", "institution": "China", "influence_tier": 2,
    },
    {
        "canonical_name": "Vladimir Putin",
        "aliases": ["Putin", "President Putin"],
        "role": "President", "institution": "Russia", "influence_tier": 2,
    },
    {
        "canonical_name": "Ursula von der Leyen",
        "aliases": ["von der Leyen", "VdL"],
        "role": "President", "institution": "European Commission", "influence_tier": 2,
    },
    {
        "canonical_name": "Philip Jefferson",
        "aliases": ["Jefferson", "Vice Chair Jefferson"],
        "role": "Vice Chair", "institution": "Federal Reserve", "influence_tier": 2,
    },
    {
        "canonical_name": "Michelle Bowman",
        "aliases": ["Bowman", "Governor Bowman"],
        "role": "Governor", "institution": "Federal Reserve", "influence_tier": 2,
    },
    {
        "canonical_name": "Adriana Kugler",
        "aliases": ["Kugler", "Governor Kugler"],
        "role": "Governor", "institution": "Federal Reserve", "influence_tier": 2,
    },
    {
        "canonical_name": "Lisa Cook",
        "aliases": ["Cook", "Governor Cook", "Lisa D. Cook"],
        "role": "Governor", "institution": "Federal Reserve", "influence_tier": 2,
    },
    {
        "canonical_name": "John Williams",
        "aliases": ["Williams", "President Williams", "NY Fed Williams"],
        "role": "President", "institution": "Federal Reserve Bank of New York", "influence_tier": 2,
    },
    {
        "canonical_name": "Christopher Waller",
        "aliases": ["Waller", "Governor Waller"],
        "role": "Governor", "institution": "Federal Reserve", "influence_tier": 2,
    },
    {
        "canonical_name": "Lael Brainard",
        "aliases": ["Brainard", "Governor Brainard"],
        "role": "Director, National Economic Council", "institution": "Federal Reserve",
        "influence_tier": 2,
    },

    # ── Tier 3: Major corporate + tech CEOs ──────────────────────────────────
    {
        "canonical_name": "Jensen Huang",
        "aliases": ["Huang", "NVIDIA CEO", "Jensen"],
        "role": "CEO", "institution": "NVIDIA", "influence_tier": 3,
    },
    {
        "canonical_name": "Elon Musk",
        "aliases": ["Musk", "Tesla CEO"],
        "role": "CEO", "institution": "Tesla / xAI / SpaceX", "influence_tier": 3,
    },
    {
        "canonical_name": "Sam Altman",
        "aliases": ["Altman", "OpenAI CEO"],
        "role": "CEO", "institution": "OpenAI", "influence_tier": 3,
    },
    {
        "canonical_name": "Satya Nadella",
        "aliases": ["Nadella", "Microsoft CEO"],
        "role": "CEO", "institution": "Microsoft", "influence_tier": 3,
    },
    {
        "canonical_name": "Tim Cook",
        "aliases": ["Tim Cook", "Apple CEO"],
        "role": "CEO", "institution": "Apple", "influence_tier": 3,
    },
    {
        "canonical_name": "Sundar Pichai",
        "aliases": ["Pichai", "Google CEO", "Alphabet CEO"],
        "role": "CEO", "institution": "Alphabet", "influence_tier": 3,
    },
    {
        "canonical_name": "Mark Zuckerberg",
        "aliases": ["Zuckerberg", "Meta CEO", "Zuck"],
        "role": "CEO", "institution": "Meta", "influence_tier": 3,
    },
    {
        "canonical_name": "Jeff Bezos",
        "aliases": ["Bezos", "Amazon founder"],
        "role": "Executive Chairman", "institution": "Amazon", "influence_tier": 3,
    },
    {
        "canonical_name": "Andy Jassy",
        "aliases": ["Jassy", "Amazon CEO"],
        "role": "CEO", "institution": "Amazon", "influence_tier": 3,
    },
    {
        "canonical_name": "Jamie Dimon",
        "aliases": ["Dimon", "JPMorgan CEO"],
        "role": "CEO", "institution": "JPMorgan Chase", "influence_tier": 3,
    },
    {
        "canonical_name": "Warren Buffett",
        "aliases": ["Buffett", "Oracle of Omaha"],
        "role": "CEO", "institution": "Berkshire Hathaway", "influence_tier": 3,
    },
    {
        "canonical_name": "Larry Fink",
        "aliases": ["Fink", "BlackRock CEO"],
        "role": "CEO", "institution": "BlackRock", "influence_tier": 3,
    },
    {
        "canonical_name": "David Solomon",
        "aliases": ["Solomon", "Goldman CEO"],
        "role": "CEO", "institution": "Goldman Sachs", "influence_tier": 3,
    },

    # ── Tier 4: Regional Fed presidents ──────────────────────────────────────
    {
        "canonical_name": "Austan Goolsbee",
        "aliases": ["Goolsbee"],
        "role": "President", "institution": "Federal Reserve Bank of Chicago", "influence_tier": 4,
    },
    {
        "canonical_name": "Neel Kashkari",
        "aliases": ["Kashkari"],
        "role": "President", "institution": "Federal Reserve Bank of Minneapolis", "influence_tier": 4,
    },
    {
        "canonical_name": "Raphael Bostic",
        "aliases": ["Bostic"],
        "role": "President", "institution": "Federal Reserve Bank of Atlanta", "influence_tier": 4,
    },
    {
        "canonical_name": "Mary Daly",
        "aliases": ["Daly"],
        "role": "President", "institution": "Federal Reserve Bank of San Francisco", "influence_tier": 4,
    },
    {
        "canonical_name": "Patrick Harker",
        "aliases": ["Harker"],
        "role": "President", "institution": "Federal Reserve Bank of Philadelphia", "influence_tier": 4,
    },
    {
        "canonical_name": "Susan Collins",
        "aliases": ["Collins"],
        "role": "President", "institution": "Federal Reserve Bank of Boston", "influence_tier": 4,
    },
    {
        "canonical_name": "Thomas Barkin",
        "aliases": ["Barkin"],
        "role": "President", "institution": "Federal Reserve Bank of Richmond", "influence_tier": 4,
    },
    {
        "canonical_name": "Alberto Musalem",
        "aliases": ["Musalem"],
        "role": "President", "institution": "Federal Reserve Bank of St. Louis", "influence_tier": 4,
    },
    {
        "canonical_name": "Loretta Mester",
        "aliases": ["Mester"],
        "role": "President (2014–2024)", "institution": "Federal Reserve Bank of Cleveland",
        "influence_tier": 4, "is_active": False,
    },
    {
        "canonical_name": "James Bullard",
        "aliases": ["Bullard"],
        "role": "President (2008–2023)", "institution": "Federal Reserve Bank of St. Louis",
        "influence_tier": 4, "is_active": False,
    },
    {
        "canonical_name": "Charles Evans",
        "aliases": ["Evans"],
        "role": "President (2007–2023)", "institution": "Federal Reserve Bank of Chicago",
        "influence_tier": 4, "is_active": False,
    },
    {
        "canonical_name": "Eric Rosengren",
        "aliases": ["Rosengren"],
        "role": "President (2007–2021)", "institution": "Federal Reserve Bank of Boston",
        "influence_tier": 4, "is_active": False,
    },
    {
        "canonical_name": "Robert Kaplan",
        "aliases": ["Kaplan"],
        "role": "President (2015–2021)", "institution": "Federal Reserve Bank of Dallas",
        "influence_tier": 4, "is_active": False,
    },
    # Historical Fed governors/vice-chairs (identified from speech archive gaps)
    {
        "canonical_name": "Stanley Fischer",
        "aliases": ["Fischer", "Vice Chairman Fischer", "Vice Chair Fischer"],
        "role": "Vice Chairman (2014–2017)", "institution": "Federal Reserve",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Daniel K. Tarullo",
        "aliases": ["Tarullo", "Governor Tarullo", "Daniel Tarullo"],
        "role": "Governor (2009–2017)", "institution": "Federal Reserve",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Randal K. Quarles",
        "aliases": ["Quarles", "Vice Chair Quarles", "Vice Chairman Quarles", "Governor Quarles"],
        "role": "Vice Chair for Supervision (2017–2021)", "institution": "Federal Reserve",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Richard H. Clarida",
        "aliases": ["Clarida", "Vice Chair Clarida", "Vice Chairman Clarida"],
        "role": "Vice Chairman (2018–2022)", "institution": "Federal Reserve",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Michael S. Barr",
        "aliases": ["Barr", "Vice Chair Barr", "Governor Barr", "Michael Barr"],
        "role": "Vice Chair for Supervision (2022–2025)", "institution": "Federal Reserve",
        "influence_tier": 2, "is_active": False,
    },
    {
        "canonical_name": "Stephen I. Miran",
        "aliases": ["Miran", "Governor Miran", "Stephen Miran"],
        "role": "Governor", "institution": "Federal Reserve",
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
