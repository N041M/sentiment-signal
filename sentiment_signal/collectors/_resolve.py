"""Shared person resolution logic for all scrapers.

Uses a two-tier approach:
  1. Exact full-name match (case-insensitive) — highest precision
  2. Multi-word name substring match — e.g. "Jerome Powell" in "Fed Chair Jerome Powell"
  3. Single-word aliases require whole-word boundary match to avoid false positives
     like "Cook" matching "Lisa D. Cook" when we want Tim Cook.
"""

from __future__ import annotations

import re

from sentiment_signal.db.models import Person


def resolve_person(speaker: str, persons: list[Person]) -> Person | None:
    speaker_lower = speaker.lower().strip()

    # Guard against empty/too-short speaker strings: an empty string is a substring
    # of every name ("" in "tim cook" is True), so without this it would match the
    # first multi-word person and silently mis-attribute the statement.
    if len(speaker_lower) < 2:
        return None

    # Also try a form with middle initials removed, so feeds that write
    # "Michelle W Bowman" / "John C Williams" still match "Michelle Bowman" etc.
    speaker_norm = _strip_middle_initials(speaker_lower)

    best: Person | None = None
    best_score = 0

    for person in persons:
        names = [person.canonical_name] + (person.aliases or [])
        score = _match_score(speaker_lower, names)
        if speaker_norm != speaker_lower:
            score = max(score, _match_score(speaker_norm, names))
        if score > best_score:
            best_score = score
            best = person

    return best if best_score > 0 else None


def _strip_middle_initials(speaker_lower: str) -> str:
    """Drop standalone single-letter tokens, e.g. 'john c williams' -> 'john williams'."""
    tokens = [t for t in speaker_lower.replace(".", " ").split() if len(t) > 1]
    return " ".join(tokens)


def _match_score(speaker_lower: str, names: list[str]) -> int:
    """Return match quality score (0 = no match, higher = better)."""
    for name in names:
        name_lower = name.lower().strip()
        words = name_lower.split()

        # Exact match — strongest signal
        if name_lower == speaker_lower:
            return 100

        # Multi-word name contained in speaker string (or vice versa)
        if len(words) >= 2:
            if name_lower in speaker_lower or speaker_lower in name_lower:
                return 10 + len(words)  # longer name match = higher confidence

        # Single-word alias: require whole-word boundary match only
        elif len(words) == 1:
            pattern = r"\b" + re.escape(name_lower) + r"\b"
            if re.search(pattern, speaker_lower):
                # Additional check: speaker string shouldn't be a different full name
                # e.g. "cook" matches "lisa d. cook" → but "lisa d. cook" has 3 words
                # while a legitimate "Cook" match would be e.g. just "Cook"
                speaker_words = speaker_lower.split()
                if len(speaker_words) <= 2:
                    return 5

    return 0
