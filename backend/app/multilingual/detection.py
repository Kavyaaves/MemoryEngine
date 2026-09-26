"""Which script and language is a piece of text in? (PLAN §6, §8)

Rule-based and deterministic:
- the *script* comes from Unicode blocks (Tamil letters live in U+0B80–0BFF, …)
- *Tanglish* (Tamil typed in Latin letters) is recognised by marker words: "da", "seri", "enna" …
- one message can mix languages, so we also return per-segment results.

    detect("நேத்து அவன் வந்து literally semma scene") → language="mixed", languages=["ta", "tanglish", "en"]
"""

import re
from dataclasses import dataclass, field

from app.multilingual.lexicon import MALAYALAM_ROMAN_MARKERS, TANGLISH_MARKERS
from app.multilingual.normalization import words

TAMIL_BLOCK = (0x0B80, 0x0BFF)
MALAYALAM_BLOCK = (0x0D00, 0x0D7F)
LATIN_LANGUAGES = {"en", "tanglish", "manglish"}


@dataclass
class Segment:
    """A run of consecutive words in the same script, e.g. the Tamil part of a mixed message."""

    text: str
    script: str
    language: str


@dataclass
class Detection:
    language: str  # ta | ml | en | tanglish | manglish | mixed | unknown
    script: str  # tamil | malayalam | latin | mixed | none
    segments: list[Segment] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)  # every language present


def char_script(ch: str) -> str | None:
    code = ord(ch)
    if TAMIL_BLOCK[0] <= code <= TAMIL_BLOCK[1]:
        return "tamil"
    if MALAYALAM_BLOCK[0] <= code <= MALAYALAM_BLOCK[1]:
        return "malayalam"
    if ch.isascii() and ch.isalpha():
        return "latin"
    return None  # digits, punctuation, emoji


def word_script(word: str) -> str | None:
    """The script most of the word's letters are in."""
    counts: dict[str, int] = {}
    for ch in word:
        script = char_script(ch)
        if script:
            counts[script] = counts.get(script, 0) + 1
    return max(counts, key=lambda s: counts[s]) if counts else None


def word_language(word: str, script: str) -> str:
    if script == "tamil":
        return "ta"
    if script == "malayalam":
        return "ml"
    lowered = word.lower()
    squeezed = re.sub(r"(.)\1{2,}", r"\1\1", lowered)  # "seriiii" → "serii"
    fully_squeezed = re.sub(r"(.)\1+", r"\1", lowered)  # "serii" → "seri"
    if squeezed in TANGLISH_MARKERS or fully_squeezed in TANGLISH_MARKERS:
        return "tanglish"
    if squeezed in MALAYALAM_ROMAN_MARKERS:
        return "manglish"
    return "en"


def _group_into_segments(tagged: list[tuple[str, str, str]]) -> list[Segment]:
    segments: list[Segment] = []
    for word, script, language in tagged:
        previous = segments[-1] if segments else None
        same_run = previous and previous.script == script and (
            previous.language == language or {previous.language, language} <= LATIN_LANGUAGES)
        if same_run:
            previous.text += " " + word
            if previous.language == "en" and language != "en":
                previous.language = language  # an English run containing Tanglish words is Tanglish
        else:
            segments.append(Segment(text=word, script=script, language=language))
    return segments


def _languages_present(tagged: list[tuple[str, str, str]]) -> list[str]:
    native = {language for _, _, language in tagged if language in ("ta", "ml")}
    languages = [lang for lang in ("ta", "ml") if lang in native]

    latin = [language for _, script, language in tagged if script == "latin"]
    if latin:
        tanglish, manglish, english = latin.count("tanglish"), latin.count("manglish"), latin.count("en")
        # Tanglish speakers mix freely with English, so two marker words (or a quarter of the
        # Latin words) are enough to call it Tanglish.
        if tanglish and tanglish >= manglish and (tanglish >= 2 or tanglish / len(latin) >= 0.25):
            languages.append("tanglish")
        elif manglish and (manglish >= 2 or manglish / len(latin) >= 0.25):
            languages.append("manglish")
        if english and (not languages or native or english / len(tagged) >= 0.3):
            languages.append("en")
    return languages or ["en"]


def detect(text: str) -> Detection:
    tagged = []  # (word, script, language)
    for word in words(text):
        script = word_script(word)
        if script is not None:  # skip pure numbers
            tagged.append((word, script, word_language(word, script)))
    if not tagged:
        return Detection(language="unknown", script="none")

    languages = _languages_present(tagged)
    scripts = {script for _, script, _ in tagged}
    return Detection(
        language=languages[0] if len(languages) == 1 else "mixed",
        script=scripts.pop() if len(scripts) == 1 else "mixed",
        segments=_group_into_segments(tagged),
        languages=languages,
    )
