"""Keyword search paths (PLAN §9):

- fts_search:  PostgreSQL full-text search — exact words, names, slang.
- trgm_search: pg_trgm fuzzy matching — typos and spelling variants ("seriii", "kuda").
"""

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory
from app.retrieval.query import Candidate, SearchFilters, content_terms, keyword_query


async def fts_search(session: AsyncSession, terms: list[str], filters: SearchFilters, limit: int = 50,
                     order: str = "rank") -> list[Candidate]:
    """order: 'rank' (best match first), 'asc' (oldest first) or 'desc' (newest first)."""
    tsquery = keyword_query(terms)
    if tsquery is None:
        return []
    rank = func.ts_rank_cd(Memory.search_tsv, tsquery, 32)  # 32 = scale the rank into 0..1
    query = filters.apply(select(Memory.id, rank).where(Memory.search_tsv.op("@@")(tsquery)))
    if order == "asc":
        query = query.order_by(Memory.timestamp.asc().nulls_last(), rank.desc())
    elif order == "desc":
        query = query.order_by(Memory.timestamp.desc().nulls_last(), rank.desc())
    else:
        query = query.order_by(rank.desc())
    rows = await session.execute(query.limit(limit))
    return [Candidate(memory_id, float(score), "fts") for memory_id, score in rows.all()]


async def fts_count(session: AsyncSession, terms: list[str], filters: SearchFilters) -> int:
    """How many memories match the keywords (counted in SQL, not by loading them)."""
    tsquery = keyword_query(terms)
    if tsquery is None:
        return 0
    query = filters.apply(select(func.count()).select_from(Memory).where(Memory.search_tsv.op("@@")(tsquery)))
    return int((await session.execute(query)).scalar_one())


async def trgm_search(session: AsyncSession, query_text: str, filters: SearchFilters, limit: int = 50,
                      threshold: float = 0.45) -> list[Candidate]:
    """Memories containing a stretch of text that *looks like* the query (by shared 3-letter chunks)."""
    terms = content_terms(query_text.split())
    if not terms:
        return []
    text = " ".join(terms)[:200]
    # The `<%` operator uses this threshold. set_config(..., true) = only for this transaction.
    # (Postgres' SET command can't take a bind parameter, set_config can.)
    await session.execute(select(func.set_config("pg_trgm.word_similarity_threshold", str(threshold), True)))
    similarity = func.word_similarity(literal(text), Memory.search_text)
    query = select(Memory.id, similarity).where(literal(text).op("<%")(Memory.search_text))
    query = filters.apply(query).order_by(similarity.desc()).limit(limit)
    rows = await session.execute(query)
    return [Candidate(memory_id, float(score), "trgm") for memory_id, score in rows.all()]
