"""Unit tests for person resolution — guards against speaker mis-attribution bugs.

Regression coverage for the Tim Cook / Lisa Cook collision documented in the
Phase 1 build log: a single-word alias must not substring-match a different
person's full name.
"""

from sentiment_signal.collectors._resolve import resolve_person
from sentiment_signal.db.models import Person


def _person(canonical_name, aliases, tier=2):
    """Construct a transient Person (no DB session needed for resolve_person)."""
    return Person(canonical_name=canonical_name, aliases=aliases, influence_tier=tier)


PERSONS = [
    _person("Tim Cook", ["Tim Cook", "Apple CEO"]),
    _person("Lisa Cook", ["Cook", "Governor Cook", "Lisa D. Cook"]),
    _person("Jerome Powell", ["Jay Powell", "Fed Chair Powell", "Powell"]),
    _person("Christine Lagarde", ["Lagarde", "ECB President Lagarde"]),
    _person("Michelle Bowman", ["Bowman", "Governor Bowman"]),
    _person("John Williams", ["John Williams", "NY Fed Williams"]),
]


class TestResolvePerson:
    def test_exact_full_name(self):
        assert resolve_person("Jerome Powell", PERSONS).canonical_name == "Jerome Powell"

    def test_multiword_substring(self):
        # Speaker string wraps the canonical name
        assert resolve_person("Fed Chair Jerome Powell", PERSONS).canonical_name == "Jerome Powell"

    def test_single_word_alias_whole_word(self):
        assert resolve_person("Powell", PERSONS).canonical_name == "Jerome Powell"

    def test_lisa_cook_not_attributed_to_tim_cook(self):
        # The documented bug: "Lisa D. Cook" must resolve to Lisa Cook, never Tim Cook
        result = resolve_person("Lisa D. Cook", PERSONS)
        assert result.canonical_name == "Lisa Cook"

    def test_bare_cook_is_ambiguous_but_resolves_to_a_cook(self):
        # Bare "Cook" is genuinely ambiguous (both canonical names contain "cook").
        # The contract is only that it resolves to one of them, never to an unrelated
        # person. The documented bug (full "Lisa D. Cook" -> Tim Cook) is covered above.
        result = resolve_person("Cook", PERSONS)
        assert result is not None
        assert result.canonical_name in {"Tim Cook", "Lisa Cook"}

    def test_no_match_returns_none(self):
        assert resolve_person("Angela Merkel", PERSONS) is None

    def test_empty_speaker_returns_none(self):
        assert resolve_person("", PERSONS) is None

    def test_case_insensitive(self):
        assert resolve_person("LAGARDE", PERSONS).canonical_name == "Christine Lagarde"

    def test_middle_initial_bowman(self):
        # BIS feed writes "Michelle W Bowman" — must match "Michelle Bowman"
        assert resolve_person("Michelle W Bowman", PERSONS).canonical_name == "Michelle Bowman"

    def test_middle_initial_williams(self):
        assert resolve_person("John C Williams", PERSONS).canonical_name == "John Williams"

    def test_middle_initial_lisa_cook_still_correct(self):
        # Normalisation must not reintroduce the Tim/Lisa collision
        assert resolve_person("Lisa D Cook", PERSONS).canonical_name == "Lisa Cook"
