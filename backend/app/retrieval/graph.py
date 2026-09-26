"""Graph search path: memories connected to the people in the question (PLAN §12).

"What did Rahul and I talk about?" → memories Rahul wrote, memories that mention him, and
memories in conversations he's part of — ranked by keyword overlap with the question.
"""

import uuid

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AliasStatus, Memory, MemoryParticipant, Person, PersonAlias, Relationship
from app.people.aliases import alias_similarity, normalize_alias
from app.retrieval.query import Candidate, SearchFilters, keyword_query

MIN_NAME_SIMILARITY = 0.8


async def resolve_people(session: AsyncSession, user_id: uuid.UUID,
                         names: list[str]) -> dict[str, list[tuple[uuid.UUID, str, float]]]:
    """For each name in a question: [(person id, display name, similarity)], best first."""
    if not names:
        return {}
    rows = (await session.execute(
        select(PersonAlias.normalized_alias, Person.id, Person.display_name)
        .join(Person, Person.id == PersonAlias.person_id)
        .where(PersonAlias.user_id == user_id, PersonAlias.status == AliasStatus.CONFIRMED,
               Person.is_self.is_(False)))).all()

    matches: dict[str, list[tuple[uuid.UUID, str, float]]] = {}
    for name in names:
        normalized = normalize_alias(name)
        best: dict[uuid.UUID, tuple[str, float]] = {}  # person id → (display name, score)
        for alias, person_id, display_name in rows:
            score = alias_similarity(normalized, alias)
            if score >= MIN_NAME_SIMILARITY and score > best.get(person_id, ("", 0.0))[1]:
                best[person_id] = (display_name, score)
        ranked = sorted(best.items(), key=lambda item: item[1][1], reverse=True)
        matches[name] = [(person_id, display, score) for person_id, (display, score) in ranked[:3]]
    return matches


async def graph_search(session: AsyncSession, terms: list[str], person_ids: list[uuid.UUID],
                       filters: SearchFilters, limit: int = 50) -> list[Candidate]:
    if not person_ids:
        return []
    their_conversations = select(Relationship.dst_id).where(
        Relationship.user_id == filters.user_id, Relationship.rel_type == "PART_OF",
        Relationship.dst_type == "CONVERSATION", Relationship.src_id.in_(person_ids))
    mentions_them = select(MemoryParticipant.memory_id).where(MemoryParticipant.person_id.in_(person_ids))
    connected = or_(Memory.author_person_id.in_(person_ids), Memory.id.in_(mentions_them),
                    Memory.conversation_id.in_(their_conversations))

    tsquery = keyword_query(terms)
    if tsquery is not None:  # rank connected memories by how well they match the question
        score = func.ts_rank_cd(Memory.search_tsv, tsquery, 32)
        query = select(Memory.id, score).where(connected, Memory.search_tsv.op("@@")(tsquery)).order_by(score.desc())
    else:  # no keywords (e.g. "show me Rahul") → most recent first
        query = select(Memory.id, literal(0.5)).where(connected).order_by(Memory.timestamp.desc().nulls_last())
    query = filters.apply(query, include_people=False).limit(limit)
    rows = await session.execute(query)
    return [Candidate(memory_id, float(score), "graph") for memory_id, score in rows.all()]


async def related_people(session: AsyncSession, user_id: uuid.UUID, person_id: uuid.UUID,
                         limit: int = 10) -> list[tuple[uuid.UUID, str, float]]:
    """People this person KNOWS, strongest connection first: [(id, name, weight)]."""
    rows = (await session.execute(
        select(Relationship.src_id, Relationship.dst_id, Relationship.weight)
        .where(Relationship.user_id == user_id, Relationship.rel_type == "KNOWS",
               or_(Relationship.src_id == person_id, Relationship.dst_id == person_id)))).all()
    weights: dict[uuid.UUID, float] = {}
    for src_id, dst_id, weight in rows:
        other = dst_id if src_id == person_id else src_id  # the edge can point either way
        weights[other] = weights.get(other, 0.0) + (weight or 0.0)
    if not weights:
        return []
    names = dict((await session.execute(select(Person.id, Person.display_name).where(
        Person.id.in_(list(weights)), Person.is_self.is_(False)))).all())
    ranked = sorted(((pid, names[pid], w) for pid, w in weights.items() if pid in names), key=lambda t: t[2], reverse=True)
    return ranked[:limit]
