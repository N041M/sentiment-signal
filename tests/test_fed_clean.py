"""Tests for the Fed footnote/nav boilerplate stripper (collectors/fed_speeches)."""

from sentiment_signal.collectors.fed_speeches import _strip_footnote_noise


def test_strips_return_to_text_anchors():
    raw = "Inflation rose. Return to text 2. Energy prices fell. Return to text"
    out = _strip_footnote_noise(raw)
    assert "return to text" not in out.lower()
    assert "Inflation rose." in out
    assert "Energy prices fell." in out


def test_strips_pdf_and_html_labels():
    out = _strip_footnote_noise("See the report (PDF) , available here (HTML) .")
    assert "(PDF)" not in out and "(HTML)" not in out
    assert "See the report" in out


def test_collapses_resulting_whitespace():
    assert "  " not in _strip_footnote_noise("a (PDF)   b   Return to text c")


def test_case_insensitive():
    assert "return to text" not in _strip_footnote_noise("x RETURN TO TEXT y").lower()


def test_noop_on_clean_text():
    clean = "The Committee decided to raise the federal funds rate by 25 basis points."
    assert _strip_footnote_noise(clean) == clean
