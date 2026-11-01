"""The incremental universe update — called after every import, and by `python -m app.universe`.

    update_universe(session, user_id, job_id)
      1. lock this user's universe          (two imports finishing together must not both create a book)
      2. find unplaced memories' pages      pages.find_new_page_keys
      3. put them on pages                  pages.place_memories       (only new/changed pages)
      4. recount those pages                pages.refresh_pages
      5. choose books                       matching.plan_books        (pure: attach or create)
      6. create books, assign pages         books.create_books, pages.assign_pages
      7. recount the touched books          books.refresh_books
      8. graph edges                        graph.save_appearances, graph.find_related_books
      9. change feed                        changes.describe
     10. commit

Work is done in chunks of CHUNK_PAGES pages, oldest first, each in its own transaction — so the
first build of a 50,000-message universe doesn't hold one enormous transaction, and books created
by one chunk are candidates for the next.

Nothing in `memories` is written. Books keep their position; a page keeps its book.
"""

import logging
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, MemoryPage, Person, UniverseChange
from app.universe import graph
from app.universe.books import create_books, load_nearby_books, refresh_books
from app.universe.changes import describe
from app.universe.matching import plan_books
from app.universe.pages import assign_pages, find_new_page_keys, page_item_counts, place_memories, refresh_pages

log = logging.getLogger(__name__)
CHUNK_PAGES = 1500


@dataclass
class UniverseStats:
    """What an update did. Stored in the ingestion job's stats["universe"] and shown on the Upload page."""

    memories_placed: int = 0
    pages_created: int = 0
    pages_updated: int = 0
    books_created: int = 0
    books_updated: int = 0
    connections: int = 0
    new_book_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = asdict(self)
        data.pop("new_book_ids")
        return data


async def lock_universe(session: AsyncSession, user_id: uuid.UUID) -> None:
    """A per-user lock that lasts until the transaction ends (commit or rollback)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"universe:{user_id}"})


async def _update_chunk(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID | None,
                        keys) -> UniverseStats:
    """Steps 3–9 for one chunk of pages. Returns what this chunk did."""
    page_ids, created_pages = await place_memories(session, user_id, keys)
    pages = await refresh_pages(session, page_ids)
    if not pages:
        return UniverseStats()
    nearby =await load_nearby_books(session, user_id, min(p.day for p in pages), max(p.day for p in pages))
    plan = plan_books(pages, nearby)
    await create_books(session, user_id, plan.new_books)
    await assign_pages(session, plan.assignments)
    new_ids = {book.id for book in plan.new_books}
    book_changes = await refresh_books(session, plan.touched_book_ids, new_ids)

    # Graph: who appears in which book, and which books resemble each other.
    book_people = {str(c.book_id): c.people for c in book_changes}
    person_ids = sorted({p for people in book_people.values() for p in people})
    before = await graph.existing_appearances(session, user_id, person_ids)
    links = graph.new_person_links(before, {book: set(people) for book, people in book_people.items()})
    await graph.save_appearances(session, user_id, book_people)
    related = await graph.find_related_books(session, user_id, [c.book_id for c in book_changes if c.created])
    await graph.save_related(session, user_id, related)

    names = dict((await session.execute(select(Person.id, Person.display_name).where(
        Person.id.in_([uuid.UUID(p) for p in person_ids])))).all()) if person_ids else {}
    mentioned_books = {uuid.UUID(b) for link in links for b in link.other_book_ids} | {r.other_id for r in related}
    titles = {str(c.book_id): c.title for c in book_changes}
    if mentioned_books:
        titles.update({str(i): t for i, t in (await session.execute(
            select(Event.id, Event.title).where(Event.id.in_(mentioned_books)))).all()})

    chunk = UniverseStats(
        memories_placed=sum(c.memories_after - c.memories_before for c in book_changes),
        pages_created=created_pages, pages_updated=len(pages) - created_pages,
        books_created=len(plan.new_books), books_updated=len(plan.updated_book_ids),
        connections=len(links) + len(related), new_book_ids=[str(i) for i in new_ids])
    session.add_all(describe(user_id, job_id, book_changes, links, related,
                             {str(k): v for k, v in names.items()}, titles, chunk.as_dict()))
    return chunk


def _add(total: UniverseStats, chunk: UniverseStats) -> None:
    for name in ("memories_placed", "pages_created", "pages_updated", "books_created", "books_updated", "connections"):
        setattr(total, name, getattr(total, name) + getattr(chunk, name))
    total.new_book_ids += chunk.new_book_ids


async def update_universe(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID | None = None) -> UniverseStats:
    """Place every unplaced memory of this user. Safe to run at any time, as often as you like:
    with nothing new it does one small query and returns."""
    stats = UniverseStats()
    while True:
        await lock_universe(session, user_id)
        keys = (await find_new_page_keys(session, user_id))[:CHUNK_PAGES]
        if not keys:
            await session.commit()  # releases the lock
            return stats
        chunk = await _update_chunk(session, user_id, job_id, keys)
        await session.commit()
        _add(stats, chunk)
        log.info("universe %s: %s", user_id, stats.as_dict())
        if chunk.memories_placed == 0:
            # Should never happen; stops an endless loop if memories can't be matched to their page.
            log.error("universe %s: %d page keys placed no memories; stopping", user_id, len(keys))
            return stats


async def prune_universe(session: AsyncSession, user_id: uuid.UUID) -> None:
    """After memories were deleted (a source was removed): recount the pages and books that lost
    memories, and delete the ones that are now empty. Existing positions are kept."""
    await lock_universe(session, user_id)
    counts = await page_item_counts(session, user_id)
    stored = dict((await session.execute(select(MemoryPage.id, MemoryPage.memory_count).where(
        MemoryPage.user_id == user_id))).all())
    empty = [page_id for page_id, count in counts.items() if count == 0]
    shrunk = [page_id for page_id, count in counts.items() if count and count != stored.get(page_id)]
    affected_books = set((await session.execute(select(MemoryPage.event_id).where(
        MemoryPage.id.in_(empty + shrunk), MemoryPage.event_id.is_not(None)))).scalars())

    if empty:
        await session.execute(delete(MemoryPage).where(MemoryPage.id.in_(empty)))
    if shrunk:
        await refresh_pages(session, shrunk)

    books_with_pages = set((await session.execute(select(MemoryPage.event_id).where(
        MemoryPage.event_id.in_(affected_books)).group_by(MemoryPage.event_id)
        .having(func.count() > 0))).scalars()) if affected_books else set()
    gone = list(affected_books - books_with_pages)
    if gone:
        titles = dict((await session.execute(select(Event.id, Event.title).where(Event.id.in_(gone)))).all())
        await graph.delete_book_edges(session, user_id, gone)
        await session.execute(delete(Event).where(Event.id.in_(gone)))
        session.add_all([UniverseChange(user_id=user_id, kind="book_removed", entity_type="EVENT", entity_id=book_id,
                                        detail={"title": titles.get(book_id, "")}) for book_id in gone])
    changes = await refresh_books(session, books_with_pages, set())
    await graph.save_appearances(session, user_id, {str(c.book_id): c.people for c in changes})
    await session.commit()
