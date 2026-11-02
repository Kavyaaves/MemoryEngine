# 0010. Keep the original text; bridge scripts with rules, not AI

- **Status:** Accepted

## Context

The chats mix Tamil, Malayalam, English and Tanglish (Tamil written in Latin letters), often inside
one message. The same word appears as "seri", "serii", "sari" and "சரி". A Latin-letter question
("naan avan kooda pona") must find a Tamil-script message ("நான் அவன் கூட போனேன்"). Translating
everything with an LLM would be slow, expensive and lossy.

## Decision

- **The original text is never changed.** It stays the source of truth.
- Each memory also gets a `search_text` that combines the normalised text, a transliteration
  (Tamil/Malayalam → colloquial Latin), Tanglish variants and phonetic keys. All search runs on that field.
- Normalisation is rules only: Unicode NFKC, case folding, collapsing repeated letters ("seriii" → "seri"),
  script detection by Unicode block, and segment-aware language tags (one message can have several).
- Spelling variants come from a seed Tanglish lexicon plus a **personal lexicon** learned from the
  user's own messages.
- Queries go through the same steps (`expand_query`), so both sides meet in the same shape.

## Consequences

- Cross-script matching works with no AI and no cost per message.
- The rules are deterministic and unit-tested.
- Meaning-level matches across languages are left to vector search and the LLM reranker.

## Where in the code

`backend/app/multilingual/` (`tanglish.py`, `transliteration.py`, `normalization.py`, `detection.py`,
`lexicon.py`, `personal_lexicon.py`). PLAN.md §6–8.
