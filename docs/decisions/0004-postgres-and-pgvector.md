# 0004. PostgreSQL is the single source of truth, with pgvector for vectors

- **Status:** Accepted. Qdrant stays an option to benchmark later.

## Context

The app needs four kinds of search: keyword, fuzzy spelling, semantic (vectors) and relationships
(graph). They could each live in their own database, but every extra database is one more thing to
host, back up, keep in sync and pay for.

## Decision

Use one PostgreSQL database for everything:

| Need | PostgreSQL feature |
|---|---|
| Tables, metadata, provenance, processing state | ordinary tables |
| Keyword search | built-in full-text search (`tsvector`) |
| Fuzzy / Tanglish spelling | `pg_trgm` extension, GIN index |
| Semantic search | `vector` extension (pgvector), HNSW index |
| Graph | a `relationships` table of generic edges between people, conversations, events, places and memories |

A separate vector database (Qdrant) is only considered if benchmarks show a real need: much larger
scale, complex filters, or a vector workload that should scale separately.

## Consequences

- Semantic results can be filtered with ordinary SQL (`WHERE user_id = … AND timestamp BETWEEN …`) in
  the same query.
- One database to back up, and one migration history.
- Filters can cut HNSW results short, so the vector scan is widened (`ef_search` 200, plus iterative
  scans on pgvector 0.8+).

## Where in the code

`backend/app/models/`, `alembic/versions/`, `retrieval/lexical.py`, `retrieval/vector.py`. PLAN.md §9 and §26.
