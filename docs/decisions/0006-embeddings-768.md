# 0006. Embeddings: text-embedding-3-small at 768 dimensions

- **Status:** Accepted. Replaces the earlier local embedding model.

## Context

Vectors from two different embedding models can't be compared, so the embedding model is effectively
part of the schema. The vector column size also has to be fixed when the table is created.

## Decision

- Every vector comes from OpenAI `text-embedding-3-small`, asked for exactly **768** dimensions.
- `vector(768)` is written into the migration. `EMBEDDING_DIM` in settings must match it.
- Each memory stores the name of the model that embedded it.
- Queries are embedded in the same normalised + transliterated shape as memories, so a Tanglish
  question and a Tamil-script message land near each other.
- Matches below a cosine similarity of 0.25 (`VECTOR_MIN_SIMILARITY`) count as noise.

## Consequences

- 768 dimensions keep the index smaller and faster than the model's full 1,536, at a small cost in quality.
- Changing the model or the size means a new migration and re-embedding every memory.
- Memories are embedded right after each import. Anything missed (an outage, a model change) is
  picked up by `python -m app.ai.embeddings` or by the worker, which runs it every 30 minutes.
  Memories are keyword-searchable before they are embedded.

## Where in the code

`backend/app/ai/embeddings.py`, `config/settings.py` (`embedding_dim`, `vector_min_similarity`),
`alembic/versions/0001_initial.py`.
