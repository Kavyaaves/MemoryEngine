"""The universe change feed: what each update changed, for the Memories page.

    describe(book_changes, person_links, related) → rows to insert   (pure)
    changes_after(user, cursor)                   → the rows after a cursor, oldest first

The page polls `GET /api/universe/changes?after=<cursor>` while an import is running. New rows
mean "refresh the universe and show a quiet notification" — the camera is never moved.

A first import can create hundreds of books, so at most MAX_ROWS_PER_UPDATE per-book rows are
written per update; one "update" row always carries the totals.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UniverseChange
from app.universe.books import BookChange
from app.universe.graph import PersonLink, RelatedBooks

MAX_ROWS_PER_UPDATE = 30


def describe(user_id: uuid.UUID, job_id: uuid.UUID | None, book_changes: list[BookChange],
             person_links: list[PersonLink], related: list[RelatedBooks], names: dict[str, str],
             titles: dict[str, str], totals: dict) -> list[UniverseChange]:
    """Change rows for one update. `names`: person id → name; `titles`: book id → title."""
    rows: list[UniverseChange] = []

    def add(kind: str, entity_type: str, entity_id, detail: dict) -> None:
        rows.append(UniverseChange(user_id=user_id, job_id=job_id, kind=kind, entity_type=entity_type,
                                   entity_id=entity_id, detail=detail))

    for change in sorted(book_changes, key=lambda c: -(c.memories_after - c.memories_before)):
        if change.created:
            add("book_created", "EVENT", change.book_id,
                {"title": change.title, "memories": change.memories_after, "pages": change.pages_after})
        elif change.memories_after > change.memories_before:
            add("book_grown", "EVENT", change.book_id,
                {"title": change.title, "added_memories": change.memories_after - change.memories_before,
                 "added_pages": max(0, change.pages_after - change.pages_before), "memories": change.memories_after})
    for link in person_links:
        add("connection", "PERSON", uuid.UUID(link.person_id),
            {"reason": "same_person", "person": names.get(link.person_id, "Someone"), "book_id": link.book_id,
             "book_title": titles.get(link.book_id, ""),
             "other_books": [{"id": b, "title": titles.get(b, "")} for b in link.other_book_ids[:5]]})
    for pair in related:
        add("connection", "EVENT", pair.book_id,
            {"reason": "similar_memories", "book_id": str(pair.book_id), "book_title": titles.get(str(pair.book_id), ""),
             "other_books": [{"id": str(pair.other_id), "title": titles.get(str(pair.other_id), "")}],
             "similarity": pair.similarity})

    rows = rows[:MAX_ROWS_PER_UPDATE]
    if book_changes or person_links or related:
        add("update", "EVENT", None, totals)
    return rows


async def changes_after(session: AsyncSession, user_id: uuid.UUID, cursor: int, limit: int = 200) -> list[UniverseChange]:
    rows = await session.execute(select(UniverseChange).where(
        UniverseChange.user_id == user_id, UniverseChange.id > cursor).order_by(UniverseChange.id).limit(limit))
    return list(rows.scalars())


async def latest_cursor(session: AsyncSession, user_id: uuid.UUID) -> int:
    row = await session.execute(select(UniverseChange.id).where(UniverseChange.user_id == user_id)
                                .order_by(UniverseChange.id.desc()).limit(1))
    return row.scalar() or 0
