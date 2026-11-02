# 0026. The Memory Universe: derived, stable, and updated incrementally

- **Status:** Accepted
- **Date:** 2026-09-27 (migration `0003`)

## Context

The Memories page shows memories as a 3D world: years along a "time river", Memory Books (events)
floating beside it, pages inside each book. This raised three problems: the layout must not jump
around after every import, building it must not touch the real data, and a large history must not
be rebuilt from scratch each time.

## Decision

- **Derived data only.** Books, pages and their positions are built from the `memories` table and
  never write to it. `python -m app.universe` can rebuild all of it.
- **Stable positions.** A book's position is computed once, when it is created, and stored:
  - `x` = days since a fixed origin (1 Jan 2000), not "your oldest memory", so importing older
    memories adds books further left without moving anything.
  - The angle around the river is a fixed **lane** per person or conversation, from a SHA-256 hash.
    Python's built-in `hash()` changes between runs, so it can't be used.
  - A new book that would overlap an existing one moves itself. Existing books never move.
- **Incremental updates** after every import: only new or changed pages and the books they touch are
  recounted, in chunks of 1,500 pages, each in its own transaction, under a per-user lock.
- Book titles are automatic first. AI titles and summaries are grounded in the book's memories, and
  the books also feed the `book` search path (Graph RAG, [0007](0007-hybrid-retrieval-rrf.md)).
- A change feed tells the page what's new ("a new book appeared").

## Consequences

- The world looks the same every time you return. Familiar books stay where you left them.
- Memories imported before the universe existed need one run of `python -m app.universe` or the
  "Build my universe" button.

## Where in the code

`backend/app/universe/` (`__init__.py` maps it, `layout.py`, `updater.py`, `books.py`, `pages.py`),
`alembic/versions/0003_memory_universe.py`, `frontend/src/universe/`.
