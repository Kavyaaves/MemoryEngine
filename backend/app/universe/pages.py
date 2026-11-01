"""Putting new memories on Memory Pages (step 1 of a universe update).

    find_new_page_keys()  which pages do the not-yet-placed memories belong to?  (one GROUP BY)
    place_memories()      create the missing pages and put the memories on them
    refresh_pages()       recount only the pages that changed → PageInfo for the planner

A page is "one thread on one local day":

    page_key = "<thread_key>:<YYYY-MM-DD>"
    thread_key = the conversation id (chats) · the source id (journals, documents) ·
                 "media" (photos, audio, video — every file is its own source, so group them by day)

A memory is "not yet placed" when it has no memory_page_items row. That makes the update
incremental and self-healing: an import only adds unplaced memories, and if an update is
interrupted, the next one simply finds the memories that are still unplaced.
Memories without a date are not placed (the universe is laid out in time); they stay searchable.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, case, cast, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import local_period
from app.models import EMBEDDING_DIM, MediaAsset, Memory, MemoryPage, MemoryPageItem, MemoryParticipant, Person
from app.universe.matching import MEDIA_THREAD, PageInfo

MEDIA_SOURCE_TYPES = ("image", "audio", "video")
PREVIEW_CHARS = 160
BATCH = 1000  # rows per INSERT/UPDATE and ids per IN (...) list


@dataclass(frozen=True)
class PageKey:
    thread_key: str
    day: date
    first_at: datetime
    last_at: datetime

    @property
    def key(self) -> str:
        return f"{self.thread_key}:{self.day.isoformat()}"


def thread_key_of():
    """SQL: the thread a memory's page belongs to (see the module docstring)."""
    return case((Memory.source_type.in_(MEDIA_SOURCE_TYPES), MEDIA_THREAD),
                else_=cast(func.coalesce(Memory.conversation_id, Memory.source_id), String))


def _unplaced(user_id: uuid.UUID):
    """This user's dated memories that are not on any page yet, with their page's thread and day.
    A subquery, so the outer queries can GROUP BY / JOIN on its thread_key and day columns."""
    placed = exists().where(MemoryPageItem.memory_id == Memory.id)
    return (select(Memory.id, Memory.timestamp, thread_key_of().label("thread_key"),
                   local_period(Memory.timestamp, "day").label("day"))
            .where(Memory.user_id == user_id, Memory.timestamp.is_not(None), ~placed)
            .subquery("unplaced"))


def _batches(items: list, size: int = BATCH):
    for start in range(0, len(items), size):
        yield items[start:start + size]


async def count_undated_unplaced(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(await session.scalar(select(func.count()).select_from(Memory).where(
        Memory.user_id == user_id, Memory.timestamp.is_(None))) or 0)


async def find_new_page_keys(session: AsyncSession, user_id: uuid.UUID) -> list[PageKey]:
    """The pages the unplaced memories belong to (existing or not), oldest first."""
    unplaced = _unplaced(user_id)
    rows = await session.execute(
        select(unplaced.c.thread_key, unplaced.c.day, func.min(unplaced.c.timestamp), func.max(unplaced.c.timestamp))
        .group_by(unplaced.c.thread_key, unplaced.c.day)
        .order_by(unplaced.c.day, unplaced.c.thread_key))
    return [PageKey(thread, date.fromisoformat(day), first, last) for thread, day, first, last in rows.all()]


async def place_memories(session: AsyncSession, user_id: uuid.UUID, keys: list[PageKey]) -> tuple[list[uuid.UUID], int]:
    """Create the pages that don't exist yet, then put every unplaced memory of those pages on
    its page. Returns (ids of all pages that received memories, how many pages were created)."""
    created = 0
    for batch in _batches(keys):
        rows = [{"id": uuid.uuid4(), "user_id": user_id, "page_key": k.key, "thread_key": k.thread_key,
                 "day": k.day, "start_at": k.first_at, "end_at": k.last_at} for k in batch]
        result = await session.execute(
            pg_insert(MemoryPage).values(rows)
            .on_conflict_do_nothing(index_elements=["user_id", "page_key"]).returning(MemoryPage.id))
        created += len(result.all())

    page_ids: list[uuid.UUID] = []
    for batch in _batches([k.key for k in keys]):
        page_ids += (await session.execute(select(MemoryPage.id).where(
            MemoryPage.user_id == user_id, MemoryPage.page_key.in_(batch)))).scalars().all()

        # INSERT INTO memory_page_items SELECT unplaced memory, its page — one statement per batch of pages.
        unplaced = _unplaced(user_id)
        page_key = func.concat(unplaced.c.thread_key, ":", unplaced.c.day)
        await session.execute(
            pg_insert(MemoryPageItem).from_select(
                ["memory_id", "page_id"],
                select(unplaced.c.id, MemoryPage.id)
                .join(MemoryPage, (MemoryPage.user_id == user_id) & (MemoryPage.page_key == page_key))
                .where(MemoryPage.page_key.in_(batch)))
            .on_conflict_do_nothing())
    return page_ids, created


async def refresh_pages(session: AsyncSession, page_ids: list[uuid.UUID]) -> list[PageInfo]:
    """Recount the given pages from their memories and return them for the planner."""
    infos: list[PageInfo] = []
    for batch in _batches(page_ids):
        is_photo = or_(Memory.source_type == "image",
                       exists().where(MediaAsset.memory_id == Memory.id, MediaAsset.kind == "photo"))
        stats = {row.page_id: row for row in (await session.execute(
            select(MemoryPageItem.page_id, func.count().label("memories"),
                   func.count(Memory.embedding).label("embedded"),
                   func.avg(Memory.embedding, type_=Vector(EMBEDDING_DIM)).label("centroid"),
                   func.min(Memory.timestamp).label("first_at"), func.max(Memory.timestamp).label("last_at"),
                   func.count().filter(is_photo).label("photos"))
            .join(Memory, Memory.id == MemoryPageItem.memory_id)
            .where(MemoryPageItem.page_id.in_(batch))
            .group_by(MemoryPageItem.page_id))).all()}

        # People: authors and people mentioned, except the user themself.
        people: dict[uuid.UUID, dict[str, int]] = {}
        for page_id, person_id, count in (await session.execute(
                select(MemoryPageItem.page_id, MemoryParticipant.person_id, func.count(func.distinct(Memory.id)))
                .join(Memory, Memory.id == MemoryPageItem.memory_id)
                .join(MemoryParticipant, MemoryParticipant.memory_id == Memory.id)
                .join(Person, Person.id == MemoryParticipant.person_id)
                .where(MemoryPageItem.page_id.in_(batch), Person.is_self.is_(False))
                .group_by(MemoryPageItem.page_id, MemoryParticipant.person_id))).all():
            people.setdefault(page_id, {})[str(person_id)] = int(count)

        # The first memory of each page, for page lists.
        previews = dict((await session.execute(
            select(MemoryPageItem.page_id, Memory.text)
            .join(Memory, Memory.id == MemoryPageItem.memory_id)
            .where(MemoryPageItem.page_id.in_(batch))
            .distinct(MemoryPageItem.page_id)
            .order_by(MemoryPageItem.page_id, Memory.timestamp))).all())

        pages = (await session.execute(select(MemoryPage.id, MemoryPage.thread_key, MemoryPage.day,
                                              MemoryPage.event_id).where(MemoryPage.id.in_(batch)))).all()
        updates = []
        for page_id, thread_key, day, event_id in pages:
            row = stats.get(page_id)
            if row is None:  # every memory of the page was deleted; updater.prune removes it
                continue
            centroid = row.centroid if row.embedded else None
            updates.append({"id": page_id, "memory_count": row.memories, "photo_count": row.photos,
                            "centroid": centroid, "centroid_count": row.embedded, "start_at": row.first_at,
                            "end_at": row.last_at, "people": people.get(page_id, {}),
                            "preview": " ".join((previews.get(page_id) or "").split())[:PREVIEW_CHARS]})
            infos.append(PageInfo(id=page_id, thread_key=thread_key, day=day, start_at=row.first_at,
                                  end_at=row.last_at, memory_count=row.memories, photo_count=row.photos,
                                  people=people.get(page_id, {}), centroid=centroid,
                                  centroid_count=row.embedded, event_id=event_id))
        if updates:
            await session.execute(update(MemoryPage), updates)
    return infos


async def assign_pages(session: AsyncSession, assignments: dict[uuid.UUID, uuid.UUID]) -> None:
    """Store the planner's page → book decisions."""
    rows = [{"id": page_id, "event_id": book_id} for page_id, book_id in assignments.items()]
    for batch in _batches(rows):
        await session.execute(update(MemoryPage), batch)


async def page_item_counts(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """memories per page, counted from memory_page_items (used after a source is deleted)."""
    rows = await session.execute(
        select(MemoryPage.id, func.count(MemoryPageItem.memory_id))
        .outerjoin(MemoryPageItem, MemoryPageItem.page_id == MemoryPage.id)
        .where(MemoryPage.user_id == user_id).group_by(MemoryPage.id))
    return {page_id: int(count) for page_id, count in rows.all()}
