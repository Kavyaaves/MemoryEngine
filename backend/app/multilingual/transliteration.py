"""Rule-based Tamil / Malayalam script → colloquial Latin transliteration.

The target is the romanisation people actually type in Tanglish (e.g.
"நான் அவன் கூட போனேன்" → "naan avan kooda ponen"), not strict ISO-15919, because
its purpose is to make native-script memories findable with romanised queries.
"""

from dataclasses import dataclass

from app.multilingual.detection import char_script

# ---------------- Tamil ----------------
TA_VOWELS = {
    "அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ee", "உ": "u", "ஊ": "oo",
    "எ": "e", "ஏ": "e", "ஐ": "ai", "ஒ": "o", "ஓ": "o", "ஔ": "au",
}
TA_CONSONANTS = {
    "க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "d", "ண": "n", "த": "th", "ந": "n",
    "ப": "p", "ம": "m", "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "zh", "ள": "l",
    "ற": "r", "ன": "n", "ஜ": "j", "ஷ": "sh", "ஸ": "s", "ஹ": "h",
}
TA_SIGNS = {
    "ா": "aa", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e", "ே": "e",
    "ை": "ai", "ொ": "o", "ோ": "o", "ௌ": "au",
}
TA_VIRAMA = "்"
TA_AYTHAM = {"ஃ": "h"}

# ---------------- Malayalam ----------------
ML_VOWELS = {
    "അ": "a", "ആ": "aa", "ഇ": "i", "ഈ": "ee", "ഉ": "u", "ഊ": "oo", "ഋ": "ru",
    "എ": "e", "ഏ": "e", "ഐ": "ai", "ഒ": "o", "ഓ": "o", "ഔ": "au",
}
ML_CONSONANTS = {
    "ക": "k", "ഖ": "kh", "ഗ": "g", "ഘ": "gh", "ങ": "ng", "ച": "ch", "ഛ": "chh", "ജ": "j",
    "ഝ": "jh", "ഞ": "nj", "ട": "t", "ഠ": "th", "ഡ": "d", "ഢ": "dh", "ണ": "n", "ത": "th",
    "ഥ": "th", "ദ": "d", "ധ": "dh", "ന": "n", "പ": "p", "ഫ": "ph", "ബ": "b", "ഭ": "bh",
    "മ": "m", "യ": "y", "ര": "r", "റ": "r", "ല": "l", "ള": "l", "ഴ": "zh", "വ": "v",
    "ശ": "sh", "ഷ": "sh", "സ": "s", "ഹ": "h",
}
ML_SIGNS = {
    "ാ": "aa", "ി": "i", "ീ": "ee", "ു": "u", "ൂ": "oo", "ൃ": "ru", "െ": "e", "േ": "e",
    "ൈ": "ai", "ൊ": "o", "ോ": "o", "ൌ": "au", "ൗ": "au",
}
ML_VIRAMA = "്"
ML_OTHER = {"ം": "m", "ഃ": "h", "ൺ": "n", "ൻ": "n", "ർ": "r", "ൽ": "l", "ൾ": "l", "ൿ": "k"}


@dataclass(frozen=True)
class ScriptTable:
    """How to read one script. Indic consonants carry a built-in "a" sound (க = "ka")."""

    vowels: dict[str, str]  # stand-alone vowels:           அ → a
    consonants: dict[str, str]  # consonants (without the "a"):  க → k
    vowel_signs: dict[str, str]  # marks that replace the "a":    கா → kaa
    virama: str  # the mark that removes the "a":  க் → k
    other: dict[str, str]  # special letters, e.g. Malayalam chillu ൻ → n


TAMIL = ScriptTable(TA_VOWELS, TA_CONSONANTS, TA_SIGNS, TA_VIRAMA, TA_AYTHAM)
MALAYALAM = ScriptTable(ML_VOWELS, ML_CONSONANTS, ML_SIGNS, ML_VIRAMA, ML_OTHER)


def _transliterate(text: str, table: ScriptTable) -> str:
    """Read left to right. After a consonant comes a virama (no vowel), a vowel sign
    (that vowel) or nothing (the built-in "a")."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        next_ch = text[i + 1] if i + 1 < len(text) else ""
        if ch in table.consonants:
            sound = table.consonants[ch]
            if next_ch == table.virama:
                out.append(sound)
                i += 2
            elif next_ch in table.vowel_signs:
                out.append(sound + table.vowel_signs[next_ch])
                i += 2
            else:
                out.append(sound + "a")
                i += 1
            continue
        if ch in table.vowels:
            out.append(table.vowels[ch])
        elif ch in table.other:
            out.append(table.other[ch])
        elif ch not in table.vowel_signs and ch != table.virama:  # drop stray marks
            out.append(ch)  # Latin letters, digits, spaces pass through
        i += 1
    return "".join(out)


def transliterate(text: str) -> str:
    """Write any Tamil/Malayalam characters in Latin letters; everything else is unchanged."""
    if not text:
        return text
    scripts = {char_script(ch) for ch in text}
    if "tamil" in scripts:
        text = _transliterate(text, TAMIL)
    if "malayalam" in scripts:
        text = _transliterate(text, MALAYALAM)
    return text


def has_native_script(text: str) -> bool:
    return any(char_script(ch) in ("tamil", "malayalam") for ch in text or "")
