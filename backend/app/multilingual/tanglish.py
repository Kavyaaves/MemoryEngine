"""Tanglish words → searchable terms. This is what makes multilingual search work without AI.

Every memory gets a `search_text` made of:
    1. its normalised text                     "serii da"
    2. a Latin transliteration (native script) "naan avan kooda ponen"
    3. the canonical Tanglish word + its Tamil spelling   "seri", "சரி"
    4. phonetic keys                           "kuda"  (so "kooda" and "kuda" meet)
Search queries are expanded the same way, so the query "naan avan kooda pona" shares
words with the message "நான் அவன் கூட போனேன்" and plain keyword search finds it.
"""

from dataclasses import dataclass, field

from app.multilingual.detection import detect
from app.multilingual.lexicon import VARIANT_GROUPS
from app.multilingual.normalization import normalize, phonetic_key, strip_urls, words
from app.multilingual.transliteration import has_native_script, transliterate


@dataclass(frozen=True)
class WordInfo:
    canonical: str  # "seri"
    native: str | None  # "சரி"
    gloss: str | None  # "okay"


def _build_indexes() -> tuple[dict[str, WordInfo], dict[str, WordInfo]]:
    """Two lookup tables from the seed lexicon: exact spelling → word, and sound → word."""
    by_spelling: dict[str, WordInfo] = {}
    for canonical, (variants, native, gloss) in VARIANT_GROUPS.items():
        info = WordInfo(canonical, native, gloss)
        by_spelling[canonical] = info
        for variant in variants:
            if len(variant) > 2:  # 1–2 letter forms ("na", "pa") collide with English words
                by_spelling.setdefault(variant, info)
        if native:
            by_spelling[native] = info

    by_sound: dict[str, WordInfo] = {}
    for spelling, info in by_spelling.items():
        if spelling.isascii():
            by_sound.setdefault(phonetic_key(spelling), info)
    return by_spelling, by_sound


WORDS_BY_SPELLING, WORDS_BY_SOUND = _build_indexes()


def lookup_word(token: str) -> WordInfo | None:
    """The known Tanglish word a token stands for: exact spelling first, then 'sounds like'."""
    token = token.lower()
    if token in WORDS_BY_SPELLING:
        return WORDS_BY_SPELLING[token]
    if token.isascii() and len(token) > 2:
        return WORDS_BY_SOUND.get(phonetic_key(token))
    return None


def extra_terms(text: str) -> list[str]:
    """Canonical forms, native spellings and phonetic keys for every word in `text`."""
    terms: list[str] = []
    for token in words(text):
        info = lookup_word(token)
        if info:
            terms.append(info.canonical)
            if info.native:
                terms.append(info.native)
        if token.isascii() and token.isalpha() and len(token) > 2:
            terms.append(phonetic_key(token))
    return terms


def unique(items: list[str]) -> list[str]:
    """Remove duplicates, keeping the first occurrence's position."""
    return list(dict.fromkeys(items))


@dataclass
class ProcessedText:
    original: str
    normalized: str
    transliteration: str | None
    language: str  # overall label, e.g. "ta" or "mixed"
    script: str
    search_text: str
    languages: list[str] = field(default_factory=list)  # every language found, e.g. ["ta", "tanglish"]
    gloss_hint: str | None = None  # e.g. "okay; tomorrow"


def process_text(text: str) -> ProcessedText:
    """Everything the database stores alongside a memory's original text."""
    normalized = normalize(text)
    detection = detect(normalized)
    transliteration = normalize(transliterate(normalized)) if has_native_script(normalized) else None

    searchable_texts = [strip_urls(normalized)]
    if transliteration:
        searchable_texts.append(strip_urls(transliteration))
    tokens: list[str] = []
    for searchable in searchable_texts:
        tokens += searchable.split()
        tokens += extra_terms(searchable)

    glosses = [info.gloss for token in words(normalized) if (info := lookup_word(token)) and info.gloss]
    return ProcessedText(
        original=text,
        normalized=normalized,
        transliteration=transliteration,
        language=detection.language,
        script=detection.script,
        search_text=" ".join(unique(tokens)),
        languages=detection.languages,
        gloss_hint="; ".join(unique(glosses)) or None,
    )


def expand_query(query: str) -> list[str]:
    """All the terms a search query should match: its words, their transliteration and variants."""
    normalized = normalize(query)
    versions = [normalized]
    if has_native_script(normalized):
        versions.append(normalize(transliterate(normalized)))
    terms: list[str] = []
    for version in versions:
        terms += words(version)
        terms += extra_terms(version)
    return unique(terms)
