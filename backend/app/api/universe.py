"""The Memory Universe (the Memories page).

    GET   /api/universe                    everything the 3D scene needs: books, years, months
    GET   /api/universe/books/{id}         one book: summary, pages, related books
    PATCH /api/universe/books/{id}         rename a book (the new title is never overwritten by AI)
    GET   /api/universe/pages/{id}         one page: its memories (original text + media)
    GET   /api/universe/memories/{id}      one memory: where it is, the messages around it, its connections
    GET   /api/universe/changes?after=N    what changed since change N (polled during imports)
    POST  /api/universe/build              place memories imported before the universe existed

Every object here is traceable: books and pages list the memory ids they are made of, and a
memory's text is returned exactly as it was imported.
"""

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, exists, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.db import get_session
from app.models import Conversation, Event, Memory, MemoryPage, MemoryPageItem, Person, Relationship, Source, User
from app.retrieval.evidence import build_evidence
from app.schemas.api import (
    BookDetailOut,
    BookOut,
    BookRenameIn,
    ConnectionOut,
    MemoryDetailOut,
    MemoryLocationOut,
    PageDetailOut,
    PageOut,
    PersonRef,
    RelatedBookOut,
    UniverseBuildOut,
    UniverseChangeOut,
    UniverseChangesOut,
    UniverseLayoutOut,
    UniverseOut,
    UniversePeriod,
)
from app.universe.changes import changes_after, latest_cursor
from app.universe.connections import memory_connections
from app.universe.layout import ORIGIN, RIVER_RADIUS, UNITS_PER_DAY, local_date
from app.universe.matching import MEDIA_THREAD
from app.workers.queue import enqueue_universe_update

router = APIRouter(prefix="/universe", tags=["universe"])
TOP_PEOPLE_PER_BOOK = 5
MAX_PAGE_MEMORIES = 300
CONTEXT_MESSAGES = 6  # messages shown before and after a memory


# ---- helpers ----------------------------------------------------------------------------

async def _person_names(session: AsyncSession, person_ids: set[str]) -> dict[str, str]:
    if not person_ids:
        return {}
    rows = await session.execute(select(cast(Person.id, String), Person.display_name).where(
        Person.id.in_([uuid.UUID(p) for p in person_ids])))
    return dict(rows.all())


def _people_refs(people: dict, names: dict[str, str], limit: int = TOP_PEOPLE_PER_BOOK) -> list[PersonRef]:
    ranked = Counter(people or {}).most_common()
    return [PersonRef(id=uuid.UUID(pid), name=names[pid], count=count) for pid, count in ranked if pid in names][:limit]


def _top_people_ids(people: dict, limit: int = TOP_PEOPLE_PER_BOOK) -> set[str]:
    return {pid for pid, _ in Counter(people or {}).most_common(limit)}


def _book_out(book: Event, names: dict[str, str]) -> BookOut:
    return BookOut(id=book.id, title=book.title, title_source=book.title_source, event_type=book.occasion_type,
                   start_at=book.start_at, end_at=book.end_at, memory_count=book.memory_count,
                   page_count=book.page_count, photo_count=book.photo_count,
                   people=_people_refs(book.people, names), position=(book.pos_x, book.pos_y, book.pos_z),
                   updated_at=book.updated_at)


async def _books_out(session: AsyncSession, books: list[Event]) -> list[BookOut]:
    names = await _person_names(session, {p for b in books for p in _top_people_ids(b.people)})
    return [_book_out(book, names) for book in books]


async def _own_book(session: AsyncSession, user: User, book_id: uuid.UUID) -> Event:
    book = await session.get(Event, book_id)
    if book is None or book.user_id != user.id:
        raise HTTPException(404, "book not found")
    return book


async def _thread_names(session: AsyncSession, thread_keys: set[str]) -> dict[str, str]:
    names = {MEDIA_THREAD: "Photos & media"}
    ids = [uuid.UUID(t) for t in thread_keys if t != MEDIA_THREAD]
    if ids:
        names.update((await session.execute(select(cast(Source.id, String), Source.name).where(Source.id.in_(ids)))).all())
        names.update((await session.execute(select(cast(Conversation.id, String), Conversation.title)
                                             .where(Conversation.id.in_(ids)))).all())
    return names


def _page_out(page: MemoryPage, names: dict[str, str], thread_names: dict[str, str]) -> PageOut:
    return PageOut(id=page.id, day=page.day.isoformat(), start_at=page.start_at, end_at=page.end_at,
                   memory_count=page.memory_count, photo_count=page.photo_count,
                   people=_people_refs(page.people, names, limit=4), preview=page.preview,
                   thread_name=thread_names.get(page.thread_key, "Memories"))


async def locate(session: AsyncSession, user_id: uuid.UUID, memory_ids: list[uuid.UUID]) -> dict[uuid.UUID, MemoryLocationOut]:
    """Where each memory is in the universe (memories not placed yet are left out)."""
    if not memory_ids:
        return {}
    rows = await session.execute(
        select(Memory.id, Memory.timestamp, MemoryPage.id, Event.id, Event.title, Event.pos_x, Event.pos_y, Event.pos_z)
        .join(MemoryPageItem, MemoryPageItem.memory_id == Memory.id)
        .join(MemoryPage, MemoryPage.id == MemoryPageItem.page_id)
        .join(Event, Event.id == MemoryPage.event_id)
        .where(Memory.user_id == user_id, Memory.id.in_(memory_ids)))
    located = {}
    for memory_id, timestamp, page_id, book_id, title, x, y, z in rows.all():
        day = local_date(timestamp)
        located[memory_id] = MemoryLocationOut(memory_id=memory_id, year=str(day.year), month=f"{day:%Y-%m}",
                                               day=day.isoformat(), book_id=book_id, book_title=title,
                                               page_id=page_id, position=(x, y, z))
    return located


# ---- routes -----------------------------------------------------------------------------

@router.get("", response_model=UniverseOut)
async def universe(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    books = list((await session.execute(select(Event).where(Event.user_id == user.id, Event.created_by == "universe")
                                        .order_by(Event.start_at))).scalars())
    # The format is inlined (literal_column) so SELECT and GROUP BY contain the identical expression.
    month_of_page = func.to_char(MemoryPage.day, literal_column("'YYYY-MM'"))
    months_rows = (await session.execute(
        select(month_of_page, func.sum(MemoryPage.memory_count))
        .where(MemoryPage.user_id == user.id).group_by(month_of_page))).all()
    book_months = Counter(f"{local_date(b.start_at):%Y-%m}" for b in books)
    months = sorted((UniversePeriod(period=period, memory_count=int(count), book_count=book_months.get(period, 0))
                     for period, count in months_rows), key=lambda p: p.period)
    years: dict[str, UniversePeriod] = {}
    for month in months:
        year = years.setdefault(month.period[:4], UniversePeriod(period=month.period[:4], memory_count=0))
        year.memory_count += month.memory_count
        year.book_count += month.book_count

    placed = exists().where(MemoryPageItem.memory_id == Memory.id)
    unplaced = await session.scalar(select(func.count()).select_from(Memory).where(
        Memory.user_id == user.id, Memory.timestamp.is_not(None), ~placed))
    undated = await session.scalar(select(func.count()).select_from(Memory).where(
        Memory.user_id == user.id, Memory.timestamp.is_(None)))
    return UniverseOut(layout=UniverseLayoutOut(origin=ORIGIN.isoformat(), units_per_day=UNITS_PER_DAY,
                                                river_radius=RIVER_RADIUS),
                       years=list(years.values()), months=months, books=await _books_out(session, books),
                       cursor=await latest_cursor(session, user.id), unplaced_memories=int(unplaced or 0),
                       undated_memories=int(undated or 0))


@router.get("/books/{book_id}", response_model=BookDetailOut)
async def book_detail(book_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    book = await _own_book(session, user, book_id)
    pages = list((await session.execute(select(MemoryPage).where(MemoryPage.event_id == book.id)
                                        .order_by(MemoryPage.start_at, MemoryPage.thread_key))).scalars())

    # Related books: through a shared person (APPEARS_IN edges) or similar memories (RELATED_TO edges).
    top_people = [uuid.UUID(p) for p in _top_people_ids(book.people)]
    shared = (await session.execute(
        select(Relationship.dst_id, Relationship.src_id).where(
            Relationship.user_id == user.id, Relationship.rel_type == "APPEARS_IN",
            Relationship.src_id.in_(top_people), Relationship.dst_id != book.id)
        .order_by(Relationship.weight.desc()).limit(12))).all() if top_people else []
    similar = (await session.execute(select(Relationship.src_id, Relationship.dst_id, Relationship.weight).where(
        Relationship.user_id == user.id, Relationship.rel_type == "RELATED_TO",
        (Relationship.src_id == book.id) | (Relationship.dst_id == book.id)))).all()

    related_ids = {other for other, _ in shared} | {dst if src == book.id else src for src, dst, _ in similar}
    others = {b.id: b for b in (await session.execute(select(Event).where(Event.id.in_(related_ids)))).scalars()}
    names = await _person_names(session, _top_people_ids(book.people)
                                | {p for page in pages for p in (page.people or {})}
                                | {p for b in others.values() for p in _top_people_ids(b.people)})
    related: dict[uuid.UUID, RelatedBookOut] = {}
    for src, dst, weight in similar:
        other = dst if src == book.id else src
        if other in others:
            related[other] = RelatedBookOut(book=_book_out(others[other], names), reason="similar_memories",
                                            label=f"Similar conversations ({weight:.2f})")
    for other, person_id in shared:
        if other in others and other not in related:
            person = names.get(str(person_id), "Someone")
            related[other] = RelatedBookOut(book=_book_out(others[other], names), reason="same_person",
                                            label=f"{person} is in both")

    thread_names = await _thread_names(session, {page.thread_key for page in pages})
    return BookDetailOut(book=_book_out(book, names),
                         summary=book.summary if book.title_source == "ai" else None,
                         summary_memory_ids=[uuid.UUID(i) for i in (book.supporting_memory_ids or [])]
                         if book.title_source == "ai" else [],
                         places=book.places or [], pages=[_page_out(p, names, thread_names) for p in pages],
                         related=sorted(related.values(), key=lambda r: r.book.start_at)[:10])


@router.patch("/books/{book_id}", response_model=BookOut)
async def rename_book(book_id: uuid.UUID, body: BookRenameIn, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    book = await _own_book(session, user, book_id)
    book.title, book.title_source = body.title.strip(), "user"
    await session.commit()
    return (await _books_out(session, [book]))[0]


@router.get("/pages/{page_id}", response_model=PageDetailOut)
async def page_detail(page_id: uuid.UUID, offset: int = 0, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    page = await session.get(MemoryPage, page_id)
    if page is None or page.user_id != user.id:
        raise HTTPException(404, "page not found")
    memory_ids = (await session.execute(
        select(Memory.id).join(MemoryPageItem, MemoryPageItem.memory_id == Memory.id)
        .where(MemoryPageItem.page_id == page.id).order_by(Memory.timestamp)
        .offset(max(0, offset)).limit(MAX_PAGE_MEMORIES))).scalars().all()
    ranked = [(memory_id, 1.0, ["universe"]) for memory_id in memory_ids]
    book = await session.get(Event, page.event_id) if page.event_id else None
    names = await _person_names(session, set(page.people or {}))
    return PageDetailOut(page=_page_out(page, names, await _thread_names(session, {page.thread_key})),
                         book_id=book.id if book else None, book_title=book.title if book else None,
                         memories=await build_evidence(session, user.id, ranked, []), total=page.memory_count)


@router.get("/memories/{memory_id}", response_model=MemoryDetailOut)
async def memory_detail(memory_id: uuid.UUID, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    memory = await session.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        raise HTTPException(404, "memory not found")

    # The original conversation around it: the messages just before and after, same thread.
    context_ids: list[uuid.UUID] = []
    if memory.timestamp is not None:
        thread = (Memory.conversation_id == memory.conversation_id) if memory.conversation_id \
            else (Memory.source_id == memory.source_id)
        base = select(Memory.id).where(Memory.user_id == user.id, thread, Memory.id != memory.id)
        before = (await session.execute(base.where(Memory.timestamp <= memory.timestamp)
                                        .order_by(Memory.timestamp.desc()).limit(CONTEXT_MESSAGES))).scalars().all()
        after = (await session.execute(base.where(Memory.timestamp >= memory.timestamp)
                                       .order_by(Memory.timestamp).limit(CONTEXT_MESSAGES))).scalars().all()
        context_ids = [*reversed(before), memory.id, *after]

    connections = await memory_connections(session, memory)
    all_ids = list(dict.fromkeys([memory.id, *context_ids, *(c.memory_id for c in connections)]))
    evidence = {e.memory_id: e for e in await build_evidence(session, user.id, [(i, 1.0, ["universe"]) for i in all_ids], [])}
    locations = await locate(session, user.id, [memory.id, *(c.memory_id for c in connections)])
    return MemoryDetailOut(
        memory=evidence[memory.id], location=locations.get(memory.id),
        context=[evidence[i] for i in context_ids if i in evidence],
        connections=[ConnectionOut(kind=c.kind, label=c.label, similarity=c.similarity, memory=evidence[c.memory_id],
                                   location=locations.get(c.memory_id))
                     for c in connections if c.memory_id in evidence])


@router.get("/changes", response_model=UniverseChangesOut)
async def changes(after: int = 0, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await changes_after(session, user.id, max(0, after))
    cursor = rows[-1].id if rows else max(after, 0)
    return UniverseChangesOut(cursor=cursor, changes=[UniverseChangeOut.model_validate(row) for row in rows])


@router.post("/build", response_model=UniverseBuildOut, status_code=202)
async def build(user: User = Depends(current_user)):
    return UniverseBuildOut(status=await enqueue_universe_update(user.id))
