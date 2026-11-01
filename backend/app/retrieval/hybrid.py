"""Hybrid search — the entry point of the retrieval layer (PLAN §9).

    search(query)
      1. expand the query          Tanglish variants + transliteration   (multilingual/)
      2. run the search paths      fts, trgm, vector, graph, temporal,   (lexical/vector/graph/temporal.py)
                                   book (Graph RAG over Memory Books)     (books.py)
      3. merge them                reciprocal rank fusion                (fusion.py)
      4. rerank                    heuristic → LLM → optional diversity   (reranker.py, diversity.py)
      5. build evidence            text, source, date, media links        (evidence.py)
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed_query
from app.ai.providers.router import AIRouter
from app.config import get_settings
from app.models import Memory
from app.multilingual.normalization import normalize
from app.multilingual.tanglish import expand_query, unique
from app.retrieval.books import book_search
from app.retrieval.diversity import MMR_POOL, mmr_order
from app.retrieval.evidence import build_evidence
from app.retrieval.fusion import FusedCandidate, rrf_fuse
from app.retrieval.graph import graph_search
from app.retrieval.lexical import fts_search, trgm_search
from app.retrieval.query import Candidate, SearchFilters
from app.retrieval.reranker import Passage, combined_score, heuristic_score, llm_rerank
from app.retrieval.temporal import temporal_search
from app.retrieval.vector import vector_search
from app.schemas.api import Evidence

MODES = {"hybrid", "fts", "trgm", "vector", "graph", "book"}
ALL_PATHS = {"fts", "trgm", "vector", "graph", "temporal", "book"}
EMBEDDING_PATHS = {"vector", "book"}  # the paths that need the question's embedding
MAX_QUERY_VARIANTS = 4
LLM_RERANK_TOP_N = 20


@dataclass
class RetrievalResult:
    evidence: list[Evidence]
    timings_ms: dict[str, int] = field(default_factory=dict)
    path_counts: dict[str, int] = field(default_factory=dict)  # candidates found per path
    degraded: bool = False  # True when semantic search was unavailable
    # The LLM reranker's best score (0..1) among the returned evidence; None when it didn't run.
    # The agent skips its "is this enough evidence?" check when this is high (agents/graph.py).
    top_rerank_score: float | None = None


class Timer:
    """Collects how long each step took, for the AI Lab page."""

    def __init__(self):
        self.ms: dict[str, int] = {}
        self._start = 0.0

    def start(self) -> None:
        self._start = time.perf_counter()

    def stop(self, name: str) -> None:
        self.ms[name] = int((time.perf_counter() - self._start) * 1000)


class HybridRetriever:
    def __init__(self, router: AIRouter):
        self.router = router
        self.settings = get_settings()

    async def search(self, session: AsyncSession, query: str, filters: SearchFilters, *, k: int | None = None,
                     mode: str = "hybrid", extra_queries: list[str] | None = None, order: str | None = None,
                     graph_person_ids: list[uuid.UUID] | None = None, reranker: str | None = None,
                     mmr_lambda: float | None = None) -> RetrievalResult:
        """
        mode:             "hybrid" (all paths) or a single path for comparison in the AI Lab
        extra_queries:    rewrites of the question (from the agent)
        order:            "first" / "last" → turns on the temporal path
        graph_person_ids: people mentioned in the question → turns on the graph path
        reranker, mmr_lambda: override the RERANKER / MMR_LAMBDA settings (the evaluation compares them)
        """
        k = k or self.settings.retrieval_top_k
        timer = Timer()

        # 1. Expand the query.
        timer.start()
        queries = unique([query, *(extra_queries or [])])[:MAX_QUERY_VARIANTS]
        terms = unique([term for q in queries for term in expand_query(q)])
        timer.stop("expand")

        # 2 + 3. Run the paths and merge them.
        paths = ALL_PATHS if mode == "hybrid" else {mode}
        results_by_path, degraded = await self._run_paths(session, paths, queries, terms, filters, order,
                                                          graph_person_ids or [], timer)
        timer.start()
        fused = rrf_fuse(results_by_path, k=self.settings.rrf_k)
        timer.stop("fuse")

        # 4. Rerank the best candidates.
        timer.start()
        ranked, llm_scores = await self._rerank(session, fused[:max(k * 3, 30)], query, terms, filters,
                                                reranker or self.settings.reranker,
                                                self.settings.mmr_lambda if mmr_lambda is None else mmr_lambda)
        timer.stop("rerank")

        # 5. Turn the top k into evidence.
        timer.start()
        evidence = await build_evidence(session, filters.user_id, ranked[:k], terms)
        timer.stop("evidence")
        judged = [llm_scores[e.memory_id] for e in evidence if e.memory_id in llm_scores]
        return RetrievalResult(evidence=evidence, timings_ms=timer.ms, degraded=degraded,
                               path_counts={path: len(found) for path, found in results_by_path.items()},
                               top_rerank_score=max(judged) if judged else None)

    async def _run_paths(self, session, paths, queries, terms, filters, order, person_ids,
                         timer: Timer) -> tuple[dict[str, list[Candidate]], bool]:
        per_path_limit = self.settings.retrieval_candidates_per_path
        results: dict[str, list[Candidate]] = {}

        # Start embedding the query now (a network call), while the SQL paths run.
        # One database session can only run one query at a time, so SQL paths run in sequence.
        embedding = None
        if paths & EMBEDDING_PATHS:
            embedding = asyncio.create_task(embed_query(self.router, " ".join(queries[:2]), filters.user_id))
        try:
            if "fts" in paths:
                timer.start()
                results["fts"] = await fts_search(session, terms, filters, limit=per_path_limit)
                timer.stop("fts")
            if "trgm" in paths:
                timer.start()
                results["trgm"] = []
                for q in queries[:2]:
                    results["trgm"] += await trgm_search(session, normalize(q), filters, limit=per_path_limit)
                timer.stop("trgm")
            if "graph" in paths and person_ids:
                timer.start()
                results["graph"] = await graph_search(session, terms, person_ids, filters, limit=per_path_limit)
                timer.stop("graph")
            if "temporal" in paths and order:
                timer.start()
                # "first trip with Rahul": the chronology only counts memories involving Rahul.
                temporal_filters = replace(filters, person_ids=person_ids) if person_ids else filters
                results["temporal"] = await temporal_search(session, terms, temporal_filters, order,
                                                            limit=per_path_limit)
                timer.stop("temporal")
            degraded = False
            if embedding is not None:
                query_vector = await embedding
                degraded = query_vector is None
                if "vector" in paths:
                    timer.start()
                    results["vector"] = await vector_search(session, query_vector, filters, limit=per_path_limit)
                    timer.stop("vector")
                if "book" in paths:
                    timer.start()
                    results["book"] = await book_search(session, query_vector, filters, limit=per_path_limit)
                    timer.stop("book")
        finally:
            if embedding is not None and not embedding.done():
                embedding.cancel()  # a SQL path failed — don't leave the request running
        return results, degraded

    async def _rerank(self, session, pool: list[FusedCandidate], query: str, terms: list[str],
                      filters: SearchFilters, reranker: str,
                      mmr_lambda: float) -> tuple[list[tuple[uuid.UUID, float, list[str]]], dict[uuid.UUID, float]]:
        """The candidates in their final order as (id, score, paths), and the LLM's 0..1 score for
        each candidate it judged (empty when the LLM reranker didn't run)."""
        if not pool:
            return [], {}
        llm_scores: dict[uuid.UUID, float] = {}
        if reranker == "none":  # evaluation baseline: the fusion order as it is
            scored = [(c, c.score) for c in pool]
        else:
            scored, llm_scores = await self._rerank_by_relevance(session, pool, query, terms, filters, reranker)
        if mmr_lambda < 1.0:
            scored = await self._diversify(session, scored, mmr_lambda)
        return [(c.memory_id, score, c.paths) for c, score in scored], llm_scores

    async def _rerank_by_relevance(self, session, pool: list[FusedCandidate], query: str, terms: list[str],
                                   filters: SearchFilters,
                                   reranker: str) -> tuple[list[tuple[FusedCandidate, float]], dict[uuid.UUID, float]]:
        """Stage 1: heuristic score for every candidate. Stage 2 (reranker="llm"): the LLM scores the top 20."""
        rows = await session.execute(
            select(Memory.id, Memory.search_text, Memory.text, Memory.timestamp, Memory.author_raw)
            .where(Memory.id.in_([c.memory_id for c in pool])))
        memories = {row.id: row for row in rows.all()}

        phrase = normalize(query)
        scored = []
        for c in pool:
            memory = memories.get(c.memory_id)
            search_text, text = (memory.search_text, memory.text) if memory else ("", "")
            scored.append((c, heuristic_score(c, search_text, text, terms, phrase)))
        scored.sort(key=lambda pair: pair[1], reverse=True)

        if reranker == "llm":
            top = scored[:LLM_RERANK_TOP_N]
            passages = []
            for c, _ in top:
                memory = memories.get(c.memory_id)
                passages.append(Passage(text=memory.text, author=memory.author_raw,
                                        date=memory.timestamp.date().isoformat() if memory.timestamp else None)
                                if memory else Passage(text=""))
            llm_scores = await llm_rerank(self.router, query, passages, filters.user_id)
            if llm_scores:
                rescored = [(c, combined_score(s, llm)) for (c, s), llm in zip(top, llm_scores, strict=True)]
                rescored.sort(key=lambda pair: pair[1], reverse=True)
                scored = rescored + scored[LLM_RERANK_TOP_N:]
                return scored, {c.memory_id: llm for (c, _), llm in zip(top, llm_scores, strict=True)}
        return scored, {}

    async def _diversify(self, session, scored: list[tuple[FusedCandidate, float]],
                         mmr_lambda: float) -> list[tuple[FusedCandidate, float]]:
        """Stage 3 (MMR_LAMBDA < 1): push near-duplicates down, using the stored embeddings."""
        top_ids = [c.memory_id for c, _ in scored[:MMR_POOL]]
        rows = await session.execute(select(Memory.id, Memory.embedding).where(
            Memory.id.in_(top_ids), Memory.embedding.is_not(None)))
        vectors = dict(rows.all())
        order = mmr_order([(c.memory_id, score) for c, score in scored], vectors, mmr_lambda)
        by_id = {c.memory_id: (c, score) for c, score in scored}
        return [by_id[memory_id] for memory_id in order]
