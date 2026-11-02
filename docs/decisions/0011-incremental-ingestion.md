# 0011. Incremental ingestion with content hashes

- **Status:** Accepted

## Context

A WhatsApp export is the whole chat every time: re-exporting a 54,000-message chat to add last week's
messages gives you all 54,000 again. Re-processing everything would repeat the embedding cost and
create duplicates.

## Decision

- Every parsed record gets a stable **content hash**, a SHA-256 of what identifies it (the source's
  fingerprint, timestamp, author and text), not of where it happened to be in the file.
- Two genuinely identical messages ("ok" twice in the same minute) get a counter added, so both are kept.
- The database enforces it: `memories` has a unique constraint on `(user_id, content_hash)`.
- Before writing, the writer looks up which hashes are already stored and only inserts the new ones.
- A whole file that was already uploaded is spotted at upload time from its SHA-256.
- Each memory records `processing_version` and the embedding model, so a change to the ingestion
  logic or the model can find the memories to re-process.

## Consequences

- Re-uploading a chat only stores, embeds and analyses the new messages.
- Each step after the writer (people, graph, embeddings, sentiment, universe) only sees new memories.
- If the hash inputs ever change, old and new hashes won't match. Bump `processing_version` and
  plan a migration.

## Where in the code

`backend/app/ingestion/records.py` (hashes), `ingestion/writer.py`, `ingestion/pipeline.py`,
`config/settings.py` (`processing_version`). PLAN.md §25.
