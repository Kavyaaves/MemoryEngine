"""Basic text normalisation (PLAN §7): Unicode → lower case → collapse repeated letters.

    normalize("SERIIII  Da") → "serii da"
    phonetic_key("kooda") == phonetic_key("kuda") == "kuda"
"""

import re
import unicodedata

# A "word": letters/digits in any script, including Tamil (U+0B80–0BFF) and Malayalam
# (U+0D00–0D7F) vowel signs, which Python's \w alone does not treat as word characters.
WORD_PATTERN = re.compile(r"[\w\u0B80-\u0BFF\u0D00-\u0D7F]+")
URL_PATTERN = re.compile(r"https?://\S+")
REPEATED_LETTER = re.compile(r"([^\W\d_])\1{2,}")  # the same letter 3+ times in a row

# Zero-width characters to delete. ZWJ/ZWNJ are kept: they change how Indic text renders.
ZERO_WIDTH_CHARS = "\u200b\u200e\u200f\ufeff\u2060"


def words(text: str) -> list[str]:
    return WORD_PATTERN.findall(text or "")


def collapse_repeats(text: str) -> str:
    """'seriiiii' → 'serii'. Two letters are kept because long vowels matter ('naan' ≠ 'nan')."""
    return REPEATED_LETTER.sub(r"\1\1", text)


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)  # one canonical encoding per character
    for ch in ZERO_WIDTH_CHARS:
        text = text.replace(ch, "")
    text = text.lower()  # only affects Latin letters; Indic scripts have no case
    text = collapse_repeats(text)
    return " ".join(text.split())  # collapse whitespace


def strip_urls(text: str) -> str:
    return URL_PATTERN.sub(" ", text)


# Spelling differences that don't change how a romanised Tamil word sounds.
PHONETIC_REPLACEMENTS = [
    ("zh", "l"), ("th", "t"), ("dh", "d"), ("sh", "s"), ("ph", "f"), ("bh", "b"), ("kh", "k"),
    ("gh", "g"), ("ch", "c"), ("ee", "i"), ("oo", "u"), ("w", "v"), ("z", "s"), ("q", "k"), ("x", "ks"),
]


def phonetic_key(token: str) -> str:
    """A rough 'sounds like' key for a romanised word, so spelling variants collide:
    kooda/kuda → kuda, theriyala/teriyala → teriyala, naan/nan → nan, yenna/enna → ena.
    Non-Latin tokens are returned unchanged."""
    key = token.lower()
    if not key.isascii() or not key.isalpha():
        return key
    for old, new in PHONETIC_REPLACEMENTS:
        key = key.replace(old, new)
    key = re.sub(r"(.)\1+", r"\1", key)  # any doubled letter → single
    key = re.sub(r"^y(?=[ae])", "", key)  # a leading y before a/e is often silent: yenna → enna
    if len(key) > 3:
        key = re.sub(r"[aeiou]+$", lambda m: m.group(0)[0], key)  # trailing vowel runs → one vowel
    return key
