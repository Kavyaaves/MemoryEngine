"""Graph edges between people and Memory Books (the "Graph" in Graph RAG), kept in the relationships table.

    (PERSON) —APPEARS_IN→ (EVENT)     weight = how many of the book's memories involve them
    (EVENT)  —RELATED_TO→ (EVENT)     weight = how similar the two books' memories are (cosine)

Both are derived from real memories: a person appears in a book only if they wrote or were
mentioned in one of its memories, and two books are related only when their stored embeddings
are close. Nothing here is guessed by a language model.

"New connection discovered" = a person who was already in some book now also appears in
another one (new_person_links), or a new RELATED_TO edge.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.graph_builder import EDGE_KEY
from app.models import Event, Relationship

CREATED_BY = "universe"
RELATED_MIN_SIMILARITY = 0.8  # books at least this similar (cosine of their average embeddings) are "related"
RELATED_MIN_DAYS_APART = 30  # …and far enough apart in time to be two different occasions
RELATED_PER_BOOK = 3


@dataclass
class PersonLink:
    """`person_id` now connects `book_id` with books they were already part of."""

    person_id: str
    book_id: str
    other_book_ids: list[str]


@dataclass
class RelatedBooks:
    book_id: uuid.UUID
    other_id: uuid.UUID
    similarity: float


def new_person_links(existing: dict[str, set[str]], book_people: dict[str, set[str]]) -> list[PersonLink]:
    """Which people link books that weren't linked through them before.

    existing:    person id → books they already appear in (before this update)
    book_people: book id → people it contains now (only the books this update touched)
    """
    links: list[PersonLink] = []
    for book_id in sorted(book_people):
        for person_id in sorted(book_people[book_id]):
            already_in = existing.get(person_id, set())
            if book_id not in already_in and already_in:
                links.append(PersonLink(person_id, book_id, sorted(already_in)))
    return links


async def existing_appearances(session: AsyncSession, user_id: uuid.UUID, person_ids: list[str]) -> dict[str, set[str]]:
    if not person_ids:
        return {}
    rows = await session.execute(select(Relationship.src_id, Relationship.dst_id).where(
        Relationship.user_id == user_id, Relationship.rel_type == "APPEARS_IN",
        Relationship.src_id.in_([uuid.UUID(p) for p in person_ids])))
    appearances: dict[str, set[str]] = {}
    for person_id, book_id in rows.all():
        appearances.setdefault(str(person_id), set()).add(str(book_id))
    return appearances


async def save_appearances(session: AsyncSession, user_id: uuid.UUID, book_people: dict[str, dict[str, int]]) -> None:
    """Upsert PERSON —APPEARS_IN→ EVENT for every person of every touched book, and drop the
    edges of people no longer in a book (possible after a source is deleted)."""
    for book_id, people in book_people.items():
        await session.execute(delete(Relationship).where(
            Relationship.user_id == user_id, Relationship.rel_type == "APPEARS_IN",
            Relationship.dst_id == uuid.UUID(book_id),
            Relationship.src_id.not_in([uuid.UUID(p) for p in people] or [uuid.UUID(int=0)])))
        edges = [{"user_id": user_id, "src_type": "PERSON", "src_id": uuid.UUID(person_id), "rel_type": "APPEARS_IN",
                  "dst_type": "EVENT", "dst_id": uuid.UUID(book_id), "weight": float(count), "confidence": 1.0,
                  "source_memory_id": None, "created_by": CREATED_BY} for person_id, count in people.items()]
        if edges:
            statement = insert(Relationship).values(edges)
            await session.execute(statement.on_conflict_do_update(
                index_elements=EDGE_KEY, set_={"weight": statement.excluded.weight}))


async def find_related_books(session: AsyncSession, user_id: uuid.UUID, book_ids: list[uuid.UUID]) -> list[RelatedBooks]:
    """For each book: up to RELATED_PER_BOOK similar books from a different time (vector search on
    the books' centroids), not yet connected by a RELATED_TO edge in either direction."""
    found: list[RelatedBooks] = []
    books = (await session.execute(select(Event.id, Event.centroid, Event.start_at).where(
        Event.id.in_(book_ids), Event.centroid.is_not(None)))).all()
    for book_id, centroid, start_at in books:
        distance = Event.centroid.cosine_distance(centroid)
        rows = await session.execute(
            select(Event.id, (1 - distance).label("similarity"), Event.start_at)
            .where(Event.user_id == user_id, Event.id != book_id, Event.centroid.is_not(None))
            .order_by(distance).limit(RELATED_PER_BOOK * 4))
        kept = 0
        for other_id, similarity, other_start in rows.all():
            if kept >= RELATED_PER_BOOK or similarity < RELATED_MIN_SIMILARITY:
                break
            if start_at and other_start and abs((start_at - other_start).days) < RELATED_MIN_DAYS_APART:
                continue  # the same period — those are neighbours, not a "related memory"
            found.append(RelatedBooks(book_id, other_id, round(float(similarity), 4)))
            kept += 1
    if not found:
        return []
    # Keep only pairs that aren't connected yet (either direction).
    pairs = {(r.book_id, r.other_id) for r in found}
    existing = (await session.execute(select(Relationship.src_id, Relationship.dst_id).where(
        Relationship.user_id == user_id, Relationship.rel_type == "RELATED_TO",
        or_(Relationship.src_id.in_([a for a, _ in pairs]), Relationship.dst_id.in_([a for a, _ in pairs]))))).all()
    connected = {(a, b) for a, b in existing} | {(b, a) for a, b in existing}
    unique: dict[frozenset, RelatedBooks] = {}
    for r in found:
        if (r.book_id, r.other_id) not in connected:
            unique.setdefault(frozenset((r.book_id, r.other_id)), r)
    return list(unique.values())


async def save_related(session: AsyncSession, user_id: uuid.UUID, related: list[RelatedBooks]) -> None:
    if not related:
        return
    edges = [{"user_id": user_id, "src_type": "EVENT", "src_id": r.book_id, "rel_type": "RELATED_TO",
              "dst_type": "EVENT", "dst_id": r.other_id, "weight": r.similarity, "confidence": r.similarity,
              "source_memory_id": None, "created_by": CREATED_BY} for r in related]
    await session.execute(insert(Relationship).values(edges).on_conflict_do_nothing())


async def delete_book_edges(session: AsyncSession, user_id: uuid.UUID, book_ids: list[uuid.UUID]) -> None:
    """Edges have no foreign key to events, so a removed book's edges are deleted here."""
    if book_ids:
        await session.execute(delete(Relationship).where(
            Relationship.user_id == user_id, Relationship.created_by == CREATED_BY,
            or_(Relationship.src_id.in_(book_ids), Relationship.dst_id.in_(book_ids))))
