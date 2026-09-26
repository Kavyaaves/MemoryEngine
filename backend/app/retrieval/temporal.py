"""Temporal search path (PLAN §11): for "first …" / "last …" questions.

Chronology is decided by SQL (ORDER BY timestamp), never by the language model:
we take keyword matches oldest-first (or newest-first) and give the earliest the top score.
(Understanding *that* a question is about "first"/"last", or "in 2023", lives in
app/agents/query_analysis.py.)
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.lexical import fts_search
from app.retrieval.query import Candidate, SearchFilters


async def temporal_search(session: AsyncSession, terms: list[str], filters: SearchFilters, order: str | None,
                          limit: int = 50) -> list[Candidate]:
    """order: 'first' or 'last' (anything else → no results from this path)."""
    if order not in ("first", "last"):
        return []
    matches = await fts_search(session, terms, filters, limit=limit, order="asc" if order == "first" else "desc")
    # Score by chronological position: 1st → 1.0, 2nd → 0.5, 3rd → 0.33 …
    return [Candidate(c.memory_id, 1.0 / (1 + position), "temporal") for position, c in enumerate(matches)]
