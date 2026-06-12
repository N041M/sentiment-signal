"""Derive a country / bloc from a person's institution.

There is no `country` column on `persons`; institutions map to countries
deterministically, so this provides a country dimension for filtering without a
schema change. Multilateral bodies map to "International", companies to
"Corporate", and unknown institutions to "Other".
"""

from __future__ import annotations

_COUNTRY_BY_INSTITUTION = {
    # United States
    "Federal Reserve": "United States",
    "U.S. Department of the Treasury": "United States",
    "U.S. Department of State": "United States",
    "U.S. Department of Defense": "United States",
    "United States": "United States",
    # United Kingdom
    "Bank of England": "United Kingdom",
    "United Kingdom": "United Kingdom",
    # Euro Area
    "European Central Bank": "Euro Area",
    "European Commission": "Euro Area",
    "European Council": "Euro Area",
    "Germany": "Germany",
    "France": "France",
    # Asia-Pacific
    "Reserve Bank of Australia": "Australia",
    "Australia": "Australia",
    "Bank of Japan": "Japan",
    "Japan": "Japan",
    "China": "China",
    # Other states
    "Bank of Canada": "Canada",
    "Russia": "Russia",
    "Ukraine": "Ukraine",
    "Israel": "Israel",
    # Multilateral
    "NATO": "International",
    "United Nations": "International",
    "International Monetary Fund": "International",
    "World Bank": "International",
    "World Trade Organization": "International",
    "OECD": "International",
    "World Economic Forum": "International",
}

# Corporations map to a "Corporate" bloc (a company is not a country)
_COMPANIES = {
    "Apple",
    "NVIDIA",
    "Tesla / xAI / SpaceX",
    "OpenAI",
    "Microsoft",
    "Alphabet",
    "Meta",
    "Amazon",
    "JPMorgan Chase",
    "Berkshire Hathaway",
    "BlackRock",
    "Goldman Sachs",
}


# Primary equity index for a central bank's mandate — for *relevance-aware* analysis
# (a speaker is only paired with the market it plausibly affects, fixing the old
# geography-blind attribution). None = no index in the dataset is clearly relevant.
_MARKET_BY_INSTITUTION = {
    "Federal Reserve": "^GSPC",
    "U.S. Department of the Treasury": "^GSPC",
    "Bank of England": "^FTSE",
    "European Central Bank": "^STOXX50E",
    "Deutsche Bundesbank": "^GDAXI",
    "Banque de France": "^FCHI",
    "Banca d'Italia": "^STOXX50E",
    "De Nederlandsche Bank": "^STOXX50E",
    "Reserve Bank of Australia": "^AXJO",
    "Bank of Japan": "^N225",
    "People's Bank of China": "000001.SS",
    "Bank of Korea": "^KS11",
}


def primary_market_for_institution(institution: str | None) -> str | None:
    """Primary equity index for a (central-bank) speaker's mandate, for relevance-aware
    pairing. None when no index in the dataset is clearly relevant (e.g. SNB, Bank of
    Canada — no Swiss/Canadian index collected). Regional Fed banks -> ^GSPC.
    """
    if not institution:
        return None
    if institution in _MARKET_BY_INSTITUTION:
        return _MARKET_BY_INSTITUTION[institution]
    if institution.startswith("Federal Reserve Bank of"):
        return "^GSPC"
    return None


def country_for_institution(institution: str | None) -> str:
    """Map an institution name to a country/bloc for filtering."""
    if not institution:
        return "Unknown"
    if institution in _COUNTRY_BY_INSTITUTION:
        return _COUNTRY_BY_INSTITUTION[institution]
    # Regional Fed banks: "Federal Reserve Bank of Chicago", etc.
    if institution.startswith("Federal Reserve Bank of"):
        return "United States"
    if institution in _COMPANIES:
        return "Corporate"
    return "Other"
