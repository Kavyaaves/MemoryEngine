"""The agent's tools (PLAN §15): deterministic operations the agent calls instead of asking the LLM.

Counting, finding people and ordering by date are exactly what SQL is good at and LLMs are
bad at. A MemoryTools object is bound to one user's database session, so a tool can never
read another user's data.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AliasStatus, Memory, Person, PersonAlias
from app.multilingual.tanglish import expand_query
from app.retrieval.address import count_address_terms
from app.retrieval.evidence import build_evidence
from app.retrieval.graph import resolve_people
from app.retrieval.hybrid import HybridRetriever, RetrievalResult
from app.retrieval.lexical import fts_count
from app.retrieval.query import SearchFilters
from app.schemas.api import Evidence


class MemoryTools:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, retriever: HybridRetriever):
        self.session = session
        self.user_id = user_id
        self.retriever = retriever

    async def search_memories(self, query: str, *, start: datetime | None = None, end: datetime | None = None,
                              person_ids: list[uuid.UUID] | None = None, source_types: list[str] | None = None,
                              extra_queries: list[str] | None = None, order: str | None = None,
                              k: int = 12) -> RetrievalResult:
        """Hybrid search. People are used by the graph path (not as a hard filter), because a
        memory about Rahul may live in a group chat he didn't write in."""
        filters = SearchFilters(user_id=self.user_id, start=start, end=end, source_types=source_types or [])
        return await self.retriever.search(self.session, query, filters, k=k, extra_queries=extra_queries,
                                           order=order, graph_person_ids=person_ids or [])

    async def resolve_person(self, name: str) -> list[tuple[uuid.UUID, str, float]]:
        """'rahul' → [(person id, "Rahul ❤\ufe0f", 1.0)]"""
        return (await resolve_people(self.session, self.user_id, [name])).get(name, [])

    async def known_aliases(self) -> dict[str, str]:
        """normalised alias → display name, for spotting people mentioned in a question."""
        rows = await self.session.execute(
            select(PersonAlias.normalized_alias, Person.display_name).join(Person, Person.id == PersonAlias.person_id)
            .where(PersonAlias.user_id == self.user_id, PersonAlias.status == AliasStatus.CONFIRMED,
                   Person.is_self.is_(False)))
        return {alias: name for alias, name in rows.all() if alias}

    async def address_terms(self, person_id: uuid.UUID, person_name: str,
                            speaker: str = "self") -> tuple[str | None, list[Evidence], str | None]:
        """How the user addresses this person (speaker="self"), or how they address the user ("them").

        Returns (a FACT line with the counts, example messages as evidence, the derived model whose
        tags were used — None when only the word list was used). (None, [], None) if nothing was found."""
        report = await count_address_terms(self.session, self.user_id, person_id, person_name, speaker)
        if not report.terms:
            return None, [], None
        # Each example is marked with how it was found: "derived" (the derived model's tags) or "address".
        path = "derived" if report.used_derived_model else "address"
        ranked = [(memory_id, 1.0, [path]) for memory_id in report.example_ids()]
        evidence = await build_evidence(self.session, self.user_id, ranked, [t.term for t in report.terms])
        return report.as_fact(), evidence, report.derived_model if report.used_derived_model else None

    async def count_memories(self, topic: str | None = None, *, start: datetime | None = None,
                             end: datetime | None = None, person_ids: list[uuid.UUID] | None = None) -> int:
        filters = SearchFilters(user_id=self.user_id, start=start, end=end, person_ids=person_ids or [])
        if topic:
            return await fts_count(self.session, expand_query(topic), filters)
        query = filters.apply(select(func.count()).select_from(Memory))
        return int((await self.session.execute(query)).scalar_one())
