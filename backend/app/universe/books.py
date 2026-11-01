"""Memory Books in the database (step 2 of a universe update).

    load_nearby_books()   existing books around the new pages' dates → BookInfo for the planner
    create_books()        insert the books the planner decided to start
    refresh_books()       recount the touched books from their pages (counts, dates, people,
                          centroid, auto title) → what changed, for the change feed

Only the touched books are read and written: an import that adds a week of messages
touches the one or two books of that week, however large the universe is.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import start_of_day
from app.models import EMBEDDING_DIM, Conversation, Event, Memory, MemoryPage, MemoryPageItem, Person, Source
from app.universe.layout import local_date
from app.universe.matching import MEDIA_THREAD, BookInfo
from app.universe.titles import auto_title

NEARBY_DAYS = 10  # books this close to the new pages are loaded (as candidates, and to avoid overlapping them)
CREATED_BY = "universe"


@dataclass
class BookChange:
    """How one touched book changed in this update (feeds the change log and job stats)."""

    book_id: uuid.UUID
    title: str
    created: bool
    memories_before: int
    memories_after: int
    pages_before: int
    pages_after: int
    people: dict[str, int]  # person id → memories, after


async def load_nearby_books(session: AsyncSession, user_id: uuid.UUID, first_day: date, last_day: date) -> list[BookInfo]:
    window_start = start_of_day(first_day - timedelta(days=NEARBY_DAYS))
    window_end = start_of_day(last_day + timedelta(days=NEARBY_DAYS + 1))
    books = (await session.execute(select(Event).where(
        Event.user_id == user_id, Event.created_by == CREATED_BY,
        Event.end_at >= window_start, Event.start_at < window_end))).scalars().all()
    if not books:
        return []
    threads: dict[uuid.UUID, set[str]] = {}
    for event_id, thread_key in (await session.execute(
            select(MemoryPage.event_id, MemoryPage.thread_key).distinct()
            .where(MemoryPage.event_id.in_([b.id for b in books])))).all():
        threads.setdefault(event_id, set()).add(thread_key)
    return [BookInfo(id=b.id, start_day=local_date(b.start_at), end_day=local_date(b.end_at), lane_key=b.lane_key,
                     position=(b.pos_x, b.pos_y, b.pos_z), memory_count=b.memory_count,
                     people=Counter(b.people or {}), thread_keys=threads.get(b.id, set()),
                     centroid=b.centroid, centroid_count=b.centroid_count) for b in books]


async def create_books(session: AsyncSession, user_id: uuid.UUID, new_books: list[BookInfo]) -> None:
    """Insert new books with a placeholder title; refresh_books fills in counts and the auto title."""
    for book in new_books:
        x, y, z = book.position
        session.add(Event(id=book.id, user_id=user_id, title="New memories", occasion_type="everyday",
                          start_at=start_of_day(book.start_day), end_at=start_of_day(book.end_day),
                          confidence=1.0, supporting_memory_ids=[], created_by=CREATED_BY, title_source="auto",
                          places=[], lane_key=book.lane_key[:100], pos_x=x, pos_y=y, pos_z=z, people={}))
    await session.flush()


async def _names(session: AsyncSession, person_ids: set[str], thread_keys: set[str]) -> tuple[dict, dict]:
    """(person id → display name, thread key → conversation title or source name)."""
    people = dict((await session.execute(select(cast(Person.id, String), Person.display_name).where(
        Person.id.in_([uuid.UUID(p) for p in person_ids])))).all()) if person_ids else {}
    ids = [uuid.UUID(t) for t in thread_keys if t != MEDIA_THREAD]
    threads: dict[str, str] = {}
    if ids:
        threads.update((await session.execute(select(cast(Source.id, String), Source.name)
                                               .where(Source.id.in_(ids)))).all())
        threads.update((await session.execute(select(cast(Conversation.id, String), Conversation.title)
                                               .where(Conversation.id.in_(ids)))).all())
    return people, threads


async def refresh_books(session: AsyncSession, book_ids: set[uuid.UUID], created: set[uuid.UUID]) -> list[BookChange]:
    """Recount `book_ids` from their pages. Books left with no pages are not touched here
    (updater.prune removes them)."""
    if not book_ids:
        return []
    ids = list(book_ids)
    before = {b.id: b for b in (await session.execute(select(Event).where(Event.id.in_(ids)))).scalars()}
    page_rows = (await session.execute(
        select(MemoryPage.event_id, MemoryPage.day, MemoryPage.start_at, MemoryPage.end_at, MemoryPage.memory_count,
               MemoryPage.photo_count, MemoryPage.people, MemoryPage.thread_key)
        .where(MemoryPage.event_id.in_(ids)))).all()
    # The centroid is the true average of the book's memory embeddings (not an average of averages).
    centroids = {row.event_id: row for row in (await session.execute(
        select(MemoryPage.event_id, func.avg(Memory.embedding, type_=Vector(EMBEDDING_DIM)).label("centroid"),
               func.count(Memory.embedding).label("embedded"))
        .join(MemoryPageItem, MemoryPageItem.page_id == MemoryPage.id)
        .join(Memory, Memory.id == MemoryPageItem.memory_id)
        .where(MemoryPage.event_id.in_(ids))
        .group_by(MemoryPage.event_id))).all()}

    per_book: dict[uuid.UUID, list] = {}
    for row in page_rows:
        per_book.setdefault(row.event_id, []).append(row)
    all_people = {person for rows in per_book.values() for row in rows for person in (row.people or {})}
    all_threads = {row.thread_key for rows in per_book.values() for row in rows}
    names, thread_names = await _names(session, all_people, all_threads)

    changes: list[BookChange] = []
    updates = []
    for book_id, rows in per_book.items():
        book = before.get(book_id)
        if book is None:
            continue
        people: Counter = Counter()
        threads: Counter = Counter()
        for row in rows:
            people.update(row.people or {})
            threads[row.thread_key] += row.memory_count
        memory_count = sum(row.memory_count for row in rows)
        start_at, end_at = min(row.start_at for row in rows), max(row.end_at for row in rows)
        media_only = set(threads) == {MEDIA_THREAD}
        values = {"id": book_id, "start_at": start_at, "end_at": end_at, "memory_count": memory_count,
                  "page_count": len(rows), "photo_count": sum(row.photo_count for row in rows),
                  "people": dict(people)}
        centroid = centroids.get(book_id)
        values["centroid"] = centroid.centroid if centroid is not None and centroid.embedded else None
        values["centroid_count"] = centroid.embedded if centroid is not None else 0
        title = book.title
        if book.title_source == "auto":
            top_people = [names[p] for p, _ in people.most_common() if p in names][:5]
            top_threads = [thread_names[t] for t, _ in threads.most_common() if t in thread_names]
            title = auto_title(top_people, top_threads, local_date(start_at), local_date(end_at), media_only)
            values.update(title=title, occasion_type="photos" if media_only else "everyday")
        updates.append(values)
        changes.append(BookChange(book_id=book_id, title=title, created=book_id in created,
                                  memories_before=0 if book_id in created else book.memory_count,
                                  memories_after=memory_count,
                                  pages_before=0 if book_id in created else book.page_count,
                                  pages_after=len(rows), people=dict(people)))
    if updates:
        # Rows have different keys (title only for auto-titled books), so update them one group at a time.
        for keys in {tuple(sorted(u)) for u in updates}:
            await session.execute(update(Event), [u for u in updates if tuple(sorted(u)) == keys])
    return changes
