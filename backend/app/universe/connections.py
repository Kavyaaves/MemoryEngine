"""Connections from one memory to others — "Visit connected memory" on the Memories page.

Worked out on demand (a few indexed queries) rather than stored, so they always reflect the
current data. Every connection points at a real stored memory and says why it is connected:

    same_event        the first memory of the previous / next page of the same book
    same_person       the previous / next time the same person wrote, outside this page
    previous_mention  the closest earlier memory in meaning (vector search, before this day)
    later_reference   the closest later memory in meaning (after this day)
    similar           other close memories in meaning, any time
    related_photo     photos in the same book (or taken the same day)

"Close in meaning" uses the stored embeddings and the same vector search as Ask, so it only
works for memories that have been embedded; the other kinds work without AI.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.timeutils import end_of_day, start_of_day
from app.models import Memory, MemoryPage, MemoryPageItem, Person
from app.retrieval.query import SearchFilters
from app.retrieval.vector import vector_search
from app.universe.layout import local_date

MIN_MEANING_SIMILARITY = 0.5  # below this, "close in meaning" is too weak to show
SIMILAR_LIMIT = 3
PHOTO_LIMIT = 4


@dataclass
class Connection:
    kind: str
    label: str
    memory_id: uuid.UUID
    similarity: float | None = None


def _similarity(score: float) -> float:
    """vector_search rescales similarity above the noise floor to 0..1; undo that for display."""
    floor = get_settings().vector_min_similarity
    return round(floor + score * (1.0 - floor), 3)


async def _page_of(session: AsyncSession, memory_id: uuid.UUID) -> MemoryPage | None:
    return (await session.execute(select(MemoryPage).join(MemoryPageItem, MemoryPageItem.page_id == MemoryPage.id)
                                  .where(MemoryPageItem.memory_id == memory_id))).scalar_one_or_none()


async def _first_memory_of(session: AsyncSession, page_id: uuid.UUID) -> uuid.UUID | None:
    return (await session.execute(select(Memory.id).join(MemoryPageItem, MemoryPageItem.memory_id == Memory.id)
                                  .where(MemoryPageItem.page_id == page_id)
                                  .order_by(Memory.timestamp).limit(1))).scalar()


async def _neighbour_pages(session: AsyncSession, page: MemoryPage) -> list[Connection]:
    found = []
    for label, condition, order in (
            ("Earlier in this book", MemoryPage.start_at < page.start_at, MemoryPage.start_at.desc()),
            ("Later in this book", MemoryPage.start_at > page.start_at, MemoryPage.start_at)):
        other = (await session.execute(select(MemoryPage.id).where(
            MemoryPage.event_id == page.event_id, MemoryPage.id != page.id, condition).order_by(order).limit(1))).scalar()
        if other and (memory_id := await _first_memory_of(session, other)):
            found.append(Connection("same_event", label, memory_id))
    return found


async def _same_person(session: AsyncSession, memory: Memory, page_ids: set[uuid.UUID]) -> list[Connection]:
    if memory.author_person_id is None or memory.timestamp is None:
        return []
    person = await session.get(Person, memory.author_person_id)
    if person is None or person.is_self:
        return []  # "the previous time you wrote" is every other message — not a useful connection
    on_page = select(MemoryPageItem.memory_id).where(MemoryPageItem.page_id.in_(page_ids))
    found = []
    for label, condition, order in (
            (f"Previous message from {person.display_name}", Memory.timestamp < memory.timestamp, Memory.timestamp.desc()),
            (f"Next message from {person.display_name}", Memory.timestamp > memory.timestamp, Memory.timestamp)):
        other = (await session.execute(select(Memory.id).where(
            Memory.user_id == memory.user_id, Memory.author_person_id == person.id, condition,
            Memory.id.not_in(on_page)).order_by(order).limit(1))).scalar()
        if other:
            found.append(Connection("same_person", label, other))
    return found


async def _close_in_meaning(session: AsyncSession, memory: Memory, exclude: set[uuid.UUID]) -> list[Connection]:
    if memory.embedding is None or memory.timestamp is None:
        return []
    vector = list(memory.embedding)
    day_start, day_end = start_of_day(local_date(memory.timestamp)), end_of_day(local_date(memory.timestamp))
    found: list[Connection] = []

    async def search(filters: SearchFilters, limit: int):
        hits = await vector_search(session, vector, filters, limit=limit + len(exclude) + 5)
        return [(c.memory_id, _similarity(c.score)) for c in hits
                if c.memory_id not in exclude and _similarity(c.score) >= MIN_MEANING_SIMILARITY][:limit]

    for memory_id, similarity in await search(SearchFilters(user_id=memory.user_id, end=day_start), 1):
        found.append(Connection("previous_mention", "Talked about something like this before", memory_id, similarity))
    for memory_id, similarity in await search(SearchFilters(user_id=memory.user_id, start=day_end), 1):
        found.append(Connection("later_reference", "Came up again later", memory_id, similarity))
    exclude = exclude | {c.memory_id for c in found}
    for memory_id, similarity in await search(SearchFilters(user_id=memory.user_id), SIMILAR_LIMIT):
        if memory_id not in exclude:
            found.append(Connection("similar", "Similar conversation", memory_id, similarity))
    return found


async def _photos(session: AsyncSession, memory: Memory, page: MemoryPage | None) -> list[Connection]:
    query = select(Memory.id).where(Memory.user_id == memory.user_id, Memory.source_type == "image",
                                    Memory.id != memory.id)
    if page is not None and page.event_id is not None:
        in_book = select(MemoryPageItem.memory_id).join(MemoryPage, MemoryPage.id == MemoryPageItem.page_id) \
            .where(MemoryPage.event_id == page.event_id)
        query = query.where(Memory.id.in_(in_book))
    elif memory.timestamp is not None:
        day = local_date(memory.timestamp)
        query = query.where(Memory.timestamp >= start_of_day(day - timedelta(days=1)),
                            Memory.timestamp < end_of_day(day + timedelta(days=1)))
    else:
        return []
    ids = (await session.execute(query.order_by(Memory.timestamp).limit(PHOTO_LIMIT))).scalars().all()
    return [Connection("related_photo", "Photo from the same time", memory_id) for memory_id in ids]


async def memory_connections(session: AsyncSession, memory: Memory) -> list[Connection]:
    """Every kind of connection for one memory, most concrete first."""
    page = await _page_of(session, memory.id)
    page_ids = {page.id} if page else set()
    on_page = set((await session.execute(select(MemoryPageItem.memory_id).where(
        MemoryPageItem.page_id.in_(page_ids)))).scalars()) if page_ids else set()

    found: list[Connection] = []
    if page is not None and page.event_id is not None:
        found += await _neighbour_pages(session, page)
    found += await _same_person(session, memory, page_ids)
    found += await _close_in_meaning(session, memory, on_page | {memory.id})
    found += await _photos(session, memory, page)

    unique: dict[uuid.UUID, Connection] = {}
    for connection in found:  # one entry per memory: the first (most concrete) reason wins
        unique.setdefault(connection.memory_id, connection)
    unique.pop(memory.id, None)
    return list(unique.values())
