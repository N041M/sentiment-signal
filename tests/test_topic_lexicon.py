"""Tests for the deterministic two-level topic labeller (nlp/topic_lexicon)."""

from sentiment_signal.nlp.topic_lexicon import _clean_terms, classify


def test_monetary_policy_main_and_sub():
    text = "The FOMC weighed a rate hike of 25 basis points as inflation stayed elevated."
    main, secondary = classify(text)
    assert main == "Monetary policy"
    assert secondary in {"Rate decisions", "Inflation & prices", "Outlook & labour market"}


def test_sanctions_main():
    text = (
        "By the authority vested in me I declare a national emergency and order blocked "
        "property of persons in Russia and Ukraine under OFAC sanction."
    )
    main, _ = classify(text)
    assert main == "Sanctions & emergencies"


def test_trade_tariffs_main():
    text = "Under section 232 I adjust imports of steel and aluminum with a new tariff schedule."
    main, _ = classify(text)
    assert main == "Trade & tariffs"


def test_ceremonial_proclamation_main():
    text = "Now therefore I hereby proclaim Flag Day and Flag Week as a national observance."
    main, _ = classify(text)
    assert main == "Ceremonial proclamations"


def test_no_keywords_is_other_with_tfidf_secondary():
    main, secondary = classify("the quick brown fox jumped over", tfidf_terms="fox / brown")
    assert main == "Other"
    assert secondary == "fox / brown"


def test_other_without_tfidf_is_general():
    main, secondary = classify("the quick brown fox jumped over")
    assert main == "Other"
    assert secondary == "general"


def test_matched_main_always_returns_named_subtheme():
    # When a main theme matches, the secondary is always one of its sub-themes
    # (never the TF-IDF fallback), even if junk TF-IDF terms are supplied.
    main, secondary = classify("inflation and price stability", tfidf_terms="pdf / vol")
    assert main == "Monetary policy"
    assert secondary != "pdf / vol"
    assert secondary in {
        "Rate decisions",
        "Inflation & prices",
        "Outlook & labour market",
        "Financial stability",
    }


def test_strongest_theme_wins():
    # Two themes present; the one with more keyword hits should win.
    text = "inflation inflation inflation cpi disinflation. one mention of steel tariff."
    main, _ = classify(text)
    assert main == "Monetary policy"


def test_clean_terms_drops_boilerplate_and_digits():
    assert _clean_terms("return text / pdf / 2024") == "general"
    assert _clean_terms(["inflation", "pdf", "42", "cpi"]) == "inflation / cpi"


def test_clean_terms_empty_is_general():
    assert _clean_terms(None) == "general"
    assert _clean_terms("") == "general"


def test_classify_is_case_insensitive():
    lower = classify("section 232 steel aluminum tariff")
    upper = classify("SECTION 232 STEEL ALUMINUM TARIFF")
    assert lower == upper


def test_central_bank_reserve_not_defense():
    # 'reserve' must not drag Fed/RBA speeches into Defense via "Federal Reserve" etc.
    text = (
        "The Federal Reserve and the Reserve Bank discussed bank reserves, "
        "inflation, the labour market, and the policy rate at the FOMC meeting."
    )
    main, _ = classify(text)
    assert main == "Monetary policy"


def test_launch_facility_not_space():
    # 'launch' must not drag a CB speech about launching a facility into Space.
    text = (
        "The central bank decided to launch a new lending facility to support "
        "financial stability and the transmission of monetary policy."
    )
    main, _ = classify(text)
    assert main == "Monetary policy"
