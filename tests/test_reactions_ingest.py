"""Tests for the keyless reaction collectors' pure logic: HN hit parsing and the
Reddit-dump speaker/window matcher."""

from datetime import UTC, datetime, timedelta

from sentiment_signal.collectors.hn_reactions import hit_to_item
from sentiment_signal.collectors.reddit_dump import (
    build_index,
    extract_text_url,
    match_line,
)

SINCE = datetime(2024, 1, 1, tzinfo=UTC)
UNTIL = datetime(2024, 1, 3, tzinfo=UTC)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


class TestHNHitParsing:
    def test_comment_hit(self):
        hit = {
            "comment_text": "Powell is signalling cuts, market disagrees strongly here",
            "created_at_i": _epoch(SINCE + timedelta(hours=5)),
            "objectID": "42",
            "points": 7,
        }
        text, url, created, points = hit_to_item(hit, SINCE, UNTIL)
        assert "signalling cuts" in text
        assert url.endswith("item?id=42")
        assert points == 7

    def test_story_hit_joins_title_and_text(self):
        hit = {
            "title": "Fed holds rates",
            "story_text": "Discussion of the decision",
            "created_at_i": _epoch(SINCE + timedelta(hours=1)),
            "objectID": "1",
            "points": None,
        }
        text, _, _, points = hit_to_item(hit, SINCE, UNTIL)
        assert text == "Fed holds rates Discussion of the decision"
        assert points == 0

    def test_out_of_window_dropped(self):
        hit = {
            "comment_text": "long enough text to pass the filter",
            "created_at_i": _epoch(UNTIL + timedelta(hours=1)),
            "objectID": "9",
        }
        assert hit_to_item(hit, SINCE, UNTIL) is None

    def test_short_or_timestampless_dropped(self):
        assert (
            hit_to_item(
                {"comment_text": "short", "created_at_i": _epoch(SINCE), "objectID": "1"},
                SINCE,
                UNTIL,
            )
            is None
        )
        assert (
            hit_to_item({"comment_text": "no timestamp on this hit at all"}, SINCE, UNTIL) is None
        )


class TestDumpMatcher:
    def _index(self):
        rows = [
            ("sid-powell", "Jerome Powell", datetime(2024, 1, 10, 12, tzinfo=UTC)),
            ("sid-lagarde", "Christine Lagarde", datetime(2024, 1, 10, 12, tzinfo=UTC)),
            ("sid-powell-2", "Jerome Powell", datetime(2024, 2, 1, 12, tzinfo=UTC)),
        ]
        return build_index(rows, window_hours=48)

    def test_name_in_window_matches(self):
        idx = self._index()
        created = _epoch(datetime(2024, 1, 11, tzinfo=UTC))
        assert match_line("i think jerome powell got this right", created, idx) == ["sid-powell"]

    def test_out_of_window_no_match(self):
        idx = self._index()
        created = _epoch(datetime(2024, 1, 20, tzinfo=UTC))
        assert match_line("jerome powell speech rerun", created, idx) == []

    def test_no_name_no_match(self):
        idx = self._index()
        created = _epoch(datetime(2024, 1, 11, tzinfo=UTC))
        assert match_line("the fed will cut rates soon", created, idx) == []

    def test_two_speakers_same_line(self):
        idx = self._index()
        created = _epoch(datetime(2024, 1, 11, tzinfo=UTC))
        got = match_line("jerome powell and christine lagarde disagree", created, idx)
        assert sorted(got) == ["sid-lagarde", "sid-powell"]

    def test_correct_statement_among_same_speaker(self):
        idx = self._index()
        created = _epoch(datetime(2024, 2, 2, tzinfo=UTC))
        assert match_line("jerome powell again", created, idx) == ["sid-powell-2"]

    def test_empty_rows_returns_none(self):
        assert build_index([], window_hours=48) is None


class TestExtractTextUrl:
    def test_comment_body(self):
        text, url = extract_text_url(
            {
                "body": "a comment long enough to keep around",
                "permalink": "/r/economics/comments/x/y/z",
            }
        )
        assert text.startswith("a comment")
        assert url == "https://reddit.com/r/economics/comments/x/y/z"

    def test_submission_title_selftext(self):
        text, _ = extract_text_url({"title": "Fed decision", "selftext": "thoughts on the cut"})
        assert text == "Fed decision\nthoughts on the cut"

    def test_deleted_dropped(self):
        assert extract_text_url({"body": "[removed]"}) is None
        assert extract_text_url({"title": "x", "selftext": "[deleted]"}) is None
