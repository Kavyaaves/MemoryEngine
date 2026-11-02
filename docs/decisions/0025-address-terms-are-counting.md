# 0025. "How do I call X?" is a counting task, not a search

- **Status:** Accepted

## Context

"How do I call Nihal most of the time?" can't be answered by search. The answer ("da", "kutta",
"chellakutty") is spread over thousands of messages that share no word with the question. In the real
data, "Nihal" appears in only 23 of the 26,231 messages written to him, while "da" appears 732 times.

## Decision

- Rules in the question analyser spot "how do I call X" and "what does X call me".
- Then the app reads **every** message in the private chat with X, in the right direction (yours to
  X, or X's to you), and counts the address words.
- Which words are address words, best first:
  1. **Derived model:** the fine-tuned tagger already tagged the message at import time
     (`meta.address_tags`, [0024](0024-one-derived-model.md)).
  2. **Baseline:** the hand-written list `ADDRESS_TERMS`, plus the person's own name.
- The result is a FACT line with counts, plus example messages as evidence. The report says which
  method was used.

## Consequences

- The answer is a correct count, not a guess from the top 12 search results.
- The word list can't tell "panni" (a pet name) from "panni vechen" (did it), or "da" as address
  from "da" as a sentence ending. That is exactly what the derived model is trained to fix.

## Where in the code

`backend/app/retrieval/address.py`, `agents/query_analysis.py`, `multilingual/lexicon.py`
(`ADDRESS_TERMS`). PLAN.md §20 F.
