from app.multilingual import detect, expand_query, normalize, phonetic_key, process_text, transliterate
from app.multilingual.normalization import collapse_repeats


def test_tamil_transliteration_matches_colloquial_romanisation():
    assert transliterate("நான் அவன் கூட போனேன்") == "naan avan kooda ponen"


def test_malayalam_transliteration():
    assert transliterate("എന്താ") == "enthaa"


def test_latin_passes_through_transliteration():
    assert transliterate("hello da") == "hello da"


def test_repeated_characters_collapse_to_two():
    assert collapse_repeats("seriiiii") == "serii"
    assert normalize("  SERIIII   Da ") == "serii da"


def test_phonetic_key_merges_spelling_variants():
    assert phonetic_key("kooda") == phonetic_key("kuda")
    assert phonetic_key("theriyala") == phonetic_key("teriyala")
    assert phonetic_key("naan") == phonetic_key("nan")


def test_detect_languages_and_scripts():
    assert detect("நான் அவன் கூட போனேன்").language == "ta"
    assert detect("എന്താ വിശേഷം").language == "ml"
    assert detect("Let us meet at 5 pm").language == "en"
    assert detect("seri da naalaiku paakalaam").language == "tanglish"


def test_code_switched_message_is_segment_aware():
    d = detect("நேத்து அவன் வந்து literally semma scene pannitaan")
    assert d.language == "mixed"
    assert d.script == "mixed"
    assert "ta" in d.languages and "tanglish" in d.languages
    assert {s.script for s in d.segments} == {"tamil", "latin"}


def test_original_text_is_preserved():
    p = process_text("Seriiii DA 😂")
    assert p.original == "Seriiii DA 😂"
    assert p.normalized == "serii da 😂"


def test_native_script_memory_is_findable_by_tanglish_query():
    memory = process_text("நான் அவன் கூட போனேன்")
    memory_tokens = set(memory.search_text.split())
    query_terms = set(expand_query("naan avan kooda pona trip"))
    assert {"naan", "avan", "kooda"} <= memory_tokens & query_terms


def test_tanglish_variants_resolve_to_canonical_and_native_form():
    p = process_text("seriiii da")
    tokens = p.search_text.split()
    assert "seri" in tokens and "சரி" in tokens


def test_tamil_query_expands_to_romanised_terms():
    terms = expand_query("கூட")
    assert "கூட" in terms and "kooda" in terms
