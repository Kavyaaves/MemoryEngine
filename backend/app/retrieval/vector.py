"""Semantic search path: memories whose meaning is close to the query (pgvector, cosine distance).

The query vector comes from app.ai.embeddings.embed_query; None means "no AI available",
in which case this path simply returns nothing and keyword search carries on alone.

Filters and the HNSW index: an HNSW index scan finds only `hnsw.ef_search` nearest vectors
(pgvector's default is 40), and the WHERE conditions (this user, a date range, a source type) are
checked *afterwards*. With the default, asking for 50 results could return at most 40, and a
date filter that keeps 1 memory in 10 would leave about 4. So before searching we
  - raise ef_search to HNSW_EF_SEARCH (a wider search: a little slower, many more candidates), and
  - on pgvector 0.8+, turn on iterative scans: the index keeps searching until enough rows pass
    the filters (up to pgvector's hnsw.max_scan_tuples limit).
Both settings are local to the current transaction (set_config(..., true)), like the trigram
threshold in lexical.py.
"""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Memory
from app.retrieval.query import Candidate, SearchFilters

HNSW_EF_SEARCH = 200  # candidates the index examines; must be at least the number of results asked for
ITERATIVE_SCAN_MIN_VERSION = (0, 8, 0)  # pgvector version that added hnsw.iterative_scan

# Whether the database's pgvector supports iterative scans. Looked up once per process: the
# extension version only changes when someone upgrades it (restart the app afterwards).
_iterative_scan_supported: bool | None = None


def parse_version(version: str | None) -> tuple[int, ...]:
    """'0.8.0' → (0, 8, 0); anything unreadable → (0,)."""
    try:
        return tuple(int(part) for part in (version or "").split("."))
    except ValueError:
        return (0,)


async def _supports_iterative_scan(session: AsyncSession) -> bool:
    global _iterative_scan_supported
    if _iterative_scan_supported is None:
        version = (await session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))).scalar()
        _iterative_scan_supported = parse_version(version) >= ITERATIVE_SCAN_MIN_VERSION
    return _iterative_scan_supported


async def _widen_index_scan(session: AsyncSession) -> None:
    """Apply the HNSW settings described at the top of this file (one round trip to the database)."""
    settings = [func.set_config("hnsw.ef_search", str(HNSW_EF_SEARCH), True)]
    if await _supports_iterative_scan(session):
        # relaxed_order: results may come back slightly out of distance order; they are re-sorted below.
        settings.append(func.set_config("hnsw.iterative_scan", "relaxed_order", True))
    await session.execute(select(*settings))


async def vector_search(session: AsyncSession, query_vector: list[float] | None, filters: SearchFilters,
                        limit: int = 50) -> list[Candidate]:
    if query_vector is None:
        return []
    settings = get_settings()
    await _widen_index_scan(session)
    distance = Memory.embedding.cosine_distance(query_vector)  # 0 = same direction, 2 = opposite
    # Only compare with vectors made by the same model — vectors from different models live
    # in unrelated spaces (this matters while a backfill is switching models).
    query = select(Memory.id, distance).where(Memory.embedding.is_not(None),
                                              Memory.embedding_model == settings.embedding_model)
    query = filters.apply(query).order_by(distance).limit(min(limit, HNSW_EF_SEARCH))
    rows = await session.execute(query)

    # Keep matches above the model's noise floor, rescaled to 0..1 so the reranker treats
    # every embedding model the same way.
    floor = settings.vector_min_similarity
    candidates = []
    for memory_id, d in rows.all():
        similarity = 1.0 - float(d)
        if similarity >= floor:
            candidates.append(Candidate(memory_id, (similarity - floor) / (1.0 - floor), "vector"))
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)  # see relaxed_order above
    return candidates
