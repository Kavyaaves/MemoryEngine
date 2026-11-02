# 0007. Hybrid retrieval: several search paths merged with weighted RRF

- **Status:** Accepted

## Context

No single kind of search finds everything in a personal chat history. Vector search misses names,
phone numbers and odd slang. Keyword search misses paraphrases and misspellings. Neither knows who
talks to whom, or what happened "before the trip". And their scores can't be compared: a trigram
similarity of 0.6 and a cosine similarity of 0.6 mean different things.

## Decision

Every search runs six paths at once, and Reciprocal Rank Fusion (RRF) merges them by **rank**, not score:

    score(memory) = Σ over paths  weight(path) / (k + rank in that path)      k = 60

| Path | Finds | Weight |
|---|---|---|
| `fts` | exact words and phrases | 1.0 |
| `trgm` | spelling variants, Tanglish | 0.6 |
| `vector` | meaning | 1.0 |
| `graph` | memories linked to the people in the question | 0.8 |
| `temporal` | memories in the asked time window | 1.2 |
| `book` | Graph RAG over Memory Books ([0026](0026-memory-universe.md)) | 0.8 |

Each path contributes up to 50 candidates. `book` weighs less than `vector` because it is also
semantic, so a memory both find gets the agreement bonus without being counted twice.

## Consequences

- A memory several paths agree on beats one that only a single path ranked first.
- Each path can be switched off in evaluation to measure what it adds ([0027](0027-evaluation.md)).

## Where in the code

`backend/app/retrieval/hybrid.py` (entry point), `retrieval/fusion.py` (`PATH_WEIGHTS`), and one file
per path in `retrieval/`. PLAN.md §9.
