"""Tamil / Malayalam / Tanglish / English text handling (PLAN §6–8). No AI involved.

    normalization.py     lower-case, collapse "seriiii", phonetic keys
    detection.py         which script / language is this text?
    transliteration.py   நான் → naan
    lexicon.py           seed list of Tanglish words and their spellings
    tanglish.py          builds `search_text` for memories and expands search queries
    personal_lexicon.py  learns the user's own spellings into the database
"""

from app.multilingual.detection import detect
from app.multilingual.normalization import normalize, phonetic_key
from app.multilingual.tanglish import ProcessedText, expand_query, process_text
from app.multilingual.transliteration import transliterate

__all__ = ["ProcessedText", "detect", "expand_query", "normalize", "phonetic_key", "process_text", "transliterate"]
