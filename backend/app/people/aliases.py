"""Comparing people's names (pure functions, no database).

    normalize_alias("Rahul ❤\ufe0f")        → "rahul"
    alias_similarity("rahu", "rahul")  → 0.85   (probably the same person — ask the user)
    alias_similarity("rahul", "rahul") → 1.0    (the same person — merge automatically)
"""

import re
import unicodedata
import uuid
from difflib import SequenceMatcher

# Scores at or above this produce an "Is X the same as Y?" suggestion.
SUGGESTION_THRESHOLD = 0.72


def normalize_alias(name: str) -> str:
    """Lower-case, drop emoji and symbols, collapse spaces. Letters of every script are kept."""
    name = unicodedata.normalize("NFKC", name)
    kept = []
    for ch in name:
        is_emoji_modifier = "\ufe00" <= ch <= "\ufe0f" or ch == "\u200d"  # variation selectors, zero-width joiner
        # L = letter, M = combining mark (needed for Tamil vowel signs), N = number, Z = space
        if unicodedata.category(ch)[0] in "LMNZ" and not is_emoji_modifier:
            kept.append(ch)
    return re.sub(r"\s+", " ", "".join(kept)).strip().casefold()


def alias_similarity(a: str, b: str) -> float:
    """How likely two normalised names refer to the same person, 0..1.

    1.0 is reserved for identical names — only those are merged without asking.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = sorted((a, b), key=len)
    longer_first_name = longer.split()[0]
    if len(shorter) == 1:  # a bare initial: "r" vs "rahul"
        return 0.75 if longer.startswith(shorter) else 0.0
    if len(shorter) >= 3 and longer_first_name.startswith(shorter):
        # "rahul" vs "rahul kumar" (same first name) or "rahu" vs "rahul" (prefix)
        return 0.9 if shorter == longer_first_name else 0.85
    if re.fullmatch(r"\+?[\d ]+", a) or re.fullmatch(r"\+?[\d ]+", b):
        return 0.0  # phone numbers must match exactly
    return round(SequenceMatcher(None, a, b).ratio() * 0.95, 3)  # general spelling similarity


def best_matches(name: str, known: dict[str, uuid.UUID], limit: int = 3) -> list[tuple[uuid.UUID, float]]:
    """Known people that `name` might be. `known` maps normalised alias → person id."""
    normalized = normalize_alias(name)
    best_score: dict[uuid.UUID, float] = {}
    for known_alias, person_id in known.items():
        score = alias_similarity(normalized, known_alias)
        if score >= SUGGESTION_THRESHOLD and score > best_score.get(person_id, 0.0):
            best_score[person_id] = score
    ranked = sorted(best_score.items(), key=lambda item: item[1], reverse=True)
    return ranked[:limit]
