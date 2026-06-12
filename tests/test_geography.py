"""Unit tests for institution -> country/bloc derivation."""

from sentiment_signal.features.geography import (
    country_for_institution,
    primary_market_for_institution,
)


class TestCountryForInstitution:
    def test_known_central_banks(self):
        assert country_for_institution("Federal Reserve") == "United States"
        assert country_for_institution("Bank of England") == "United Kingdom"
        assert country_for_institution("European Central Bank") == "Euro Area"
        assert country_for_institution("Reserve Bank of Australia") == "Australia"

    def test_regional_fed_banks(self):
        assert country_for_institution("Federal Reserve Bank of Chicago") == "United States"
        assert country_for_institution("Federal Reserve Bank of New York") == "United States"

    def test_head_of_state_institutions_are_countries(self):
        assert country_for_institution("United States") == "United States"
        assert country_for_institution("Ukraine") == "Ukraine"
        assert country_for_institution("Russia") == "Russia"

    def test_multilateral_bodies_are_international(self):
        assert country_for_institution("United Nations") == "International"
        assert country_for_institution("NATO") == "International"
        assert country_for_institution("International Monetary Fund") == "International"

    def test_companies_are_corporate(self):
        assert country_for_institution("Apple") == "Corporate"
        assert country_for_institution("NVIDIA") == "Corporate"

    def test_none_and_unknown(self):
        assert country_for_institution(None) == "Unknown"
        assert country_for_institution("") == "Unknown"
        assert country_for_institution("Some New Central Bank") == "Other"


class TestPrimaryMarketForInstitution:
    def test_known_central_banks_map_to_their_index(self):
        assert primary_market_for_institution("Federal Reserve") == "^GSPC"
        assert primary_market_for_institution("Bank of Japan") == "^N225"
        assert primary_market_for_institution("European Central Bank") == "^STOXX50E"
        assert primary_market_for_institution("Reserve Bank of Australia") == "^AXJO"

    def test_regional_fed_maps_to_us(self):
        assert primary_market_for_institution("Federal Reserve Bank of Atlanta") == "^GSPC"

    def test_no_relevant_index_returns_none(self):
        assert primary_market_for_institution("Swiss National Bank") is None
        assert primary_market_for_institution("Bank of Canada") is None
        assert primary_market_for_institution(None) is None
        assert primary_market_for_institution("United Nations") is None
