"""Titles and summaries of Memory Books.

Two kinds, and the UI always says which one it is showing:

    auto   built from facts only: the people in the book, its conversation and its dates,
           e.g. "Rahul & Priya · 12–18 Jun 2024". Always available, no AI.
    ai     an LLM reads a sample of the book's memories (evenly spread over its pages) and writes
           a title, a type and a 2–3 sentence summary. The sample's memory ids are stored on the
           book (supporting_memory_ids), so every summary can be traced to what the model saw.

Guards against invented details:
- The model sees nothing but the sampled memories, marked as untrusted data.
- A place is kept only if its name literally appears in one of those memories.
- A book the user renamed (title_source "user") is never overwritten.

Naming is the only expensive step of the universe, so it runs after the structural update is
committed, holds no database connection while the model works, and names at most
MAX_AI_TITLES_PER_RUN books per run; the rest keep their auto title until the next run
(`python -m app.universe titles`, or the worker's half-hourly job).
"""

import logging
import uuid
from datetime import date
from html import escape
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.ai.prompts import BOOK_TITLE_SYSTEM
from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import AIRouter, get_router
from app.db import SessionLocal
from app.models import Event, Memory, MemoryPage, MemoryPageItem, UniverseChange
from app.multilingual.normalization import normalize
from app.universe.layout import local_date

log = logging.getLogger(__name__)
MAX_AI_TITLES_PER_RUN = 40
SAMPLE_SIZE = 40  # memories shown to the model per book
SAMPLE_TEXT_CHARS = 300
RETITLE_GROWTH = 1.5  # an AI title is rewritten once the book has grown to 1.5× the memories it was written from
MIN_MEMORIES_FOR_AI = 5  # a book with fewer memories keeps its auto title (too little to summarise)

EventType = Literal["trip", "celebration", "work", "study", "relationship", "family", "move", "health",
                    "everyday", "photos", "other"]


class BookTitle(BaseModel):
    """What the model returns for one book."""

    title: str = Field(description="3-6 words naming the event or period, e.g. 'Andhra trip with college friends'")
    event_type: EventType = "everyday"
    summary: str = Field(description="2-3 sentences, only facts stated in the memories")
    places: list[str] = Field(default_factory=list, description="place names written in the memories, as written")


# ---- auto titles (no AI) ------------------------------------------------------------------

def format_range(start: date, end: date) -> str:
    """14 Jun 2024 · 12–18 Jun 2024 · 28 Jun – 3 Jul 2024 · 28 Dec 2024 – 2 Jan 2025"""
    if start == end:
        return f"{start.day} {start:%b %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"
    return f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y}"


def auto_title(people_names: list[str], thread_names: list[str], start: date, end: date, media_only: bool) -> str:
    """people_names: most involved first. thread_names: the book's conversations / sources."""
    when = format_range(start, end)
    if media_only:
        return f"Photos & media · {when}"
    if len(people_names) == 1:
        who = people_names[0]
    elif len(people_names) == 2:
        who = f"{people_names[0]} & {people_names[1]}"
    elif people_names:
        who = f"{people_names[0]}, {people_names[1]} +{len(people_names) - 2}"
    else:
        who = thread_names[0] if thread_names else "Memories"
    return f"{who} · {when}"[:500]


# ---- AI titles -----------------------------------------------------------------------------

def grounded_places(places: list[str], texts: list[str]) -> list[str]:
    """Keep only the places whose name appears in the memories (case and spelling-normalised)."""
    haystack = normalize(" \n ".join(texts))
    kept: list[str] = []
    for place in places:
        name = place.strip()
        if len(name) >= 3 and normalize(name) in haystack and name not in kept:
            kept.append(name[:100])
    return kept[:8]


def spread_sample(ids: list, size: int) -> list:
    """`size` items spread evenly over `ids` (already in time order), always including the first and last."""
    if len(ids) <= size:
        return list(ids)
    step = (len(ids) - 1) / (size - 1)
    return [ids[round(i * step)] for i in range(size)]


def needs_ai_title(book: Event) -> bool:
    if book.title_source == "user" or book.memory_count < MIN_MEMORIES_FOR_AI:
        return False
    if book.title_source == "auto":
        return True
    return book.memory_count >= book.summarized_count * RETITLE_GROWTH


def _prompt(book: Event, samples: list[tuple]) -> str:
    lines = [f"Book dates: {format_range(local_date(book.start_at), local_date(book.end_at))}",
             f"Memories in the book: {book.memory_count} (a sample of {len(samples)} follows)", "<memories>"]
    for number, (_, timestamp, author, text) in enumerate(samples, start=1):
        when = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "undated"
        lines.append(f'<memory id="{number}" date="{when}" author="{escape(author or "")}">'
                     f"{escape((text or '')[:SAMPLE_TEXT_CHARS])}</memory>")
    lines.append("</memories>")
    return "\n".join(lines)


async def _load_samples(book_id: uuid.UUID) -> tuple[Event | None, list[tuple]]:
    """(the book, [(memory id, timestamp, author, text)]) — a quick read; the session is closed afterwards."""
    async with SessionLocal() as session:
        book = await session.get(Event, book_id)
        if book is None:
            return None, []
        rows = (await session.execute(
            select(Memory.id, Memory.timestamp, Memory.author_raw, Memory.text)
            .join(MemoryPageItem, MemoryPageItem.memory_id == Memory.id)
            .join(MemoryPage, MemoryPage.id == MemoryPageItem.page_id)
            .where(MemoryPage.event_id == book_id, Memory.text != "")
            .order_by(Memory.timestamp))).all()
    # Skip one-word messages ("ok", "hmm"): they tell the model nothing.
    meaningful = [row for row in rows if len((row.text or "").split()) >= 3] or rows
    return book, spread_sample(meaningful, SAMPLE_SIZE)


async def name_book(router: AIRouter, book_id: uuid.UUID) -> bool | None:
    """Write an AI title/summary for one book. True = named, False = AI unavailable (stop for now),
    None = skipped (the book vanished, has no text, or the model returned no title)."""
    book, samples = await _load_samples(book_id)
    if book is None or not samples:
        return None
    try:
        result = await router.structured("fast", BookTitle, [("system", BOOK_TITLE_SYSTEM),
                                                              ("user", _prompt(book, samples))], user_id=book.user_id)
    except AIUnavailable as exc:
        log.info("book naming paused: %s", str(exc)[:200])
        return False

    title = " ".join(result.title.split())[:120]
    if not title:
        return None
    async with SessionLocal() as session:
        book = await session.get(Event, book_id)
        if book is None or book.title_source == "user":  # deleted, or renamed by the user meanwhile
            return None
        book.title = title
        book.title_source = "ai"
        book.occasion_type = result.event_type
        book.summary = " ".join(result.summary.split())[:1200] or None
        book.places = grounded_places(result.places, [text for _, _, _, text in samples])
        book.supporting_memory_ids = [str(memory_id) for memory_id, _, _, _ in samples]
        book.summarized_count = book.memory_count
        session.add(UniverseChange(user_id=book.user_id, kind="book_renamed", entity_type="EVENT",
                                   entity_id=book.id, detail={"title": title}))
        await session.commit()
    return True


async def name_books(user_id: uuid.UUID | None = None, prefer: list[uuid.UUID] | None = None,
                     limit: int = MAX_AI_TITLES_PER_RUN) -> int:
    """Give up to `limit` books an AI title: the `prefer`red ones first (e.g. just created),
    then the biggest books still on an auto title. Returns how many were named."""
    router = get_router()
    if limit <= 0 or not router.available("fast"):
        return 0
    async with SessionLocal() as session:
        query = select(Event).where(Event.created_by == "universe", Event.memory_count >= MIN_MEMORIES_FOR_AI,
                                    or_(Event.title_source == "auto", Event.title_source == "ai"))
        if user_id:
            query = query.where(Event.user_id == user_id)
        books = [book for book in (await session.execute(query.order_by(Event.memory_count.desc()).limit(limit * 5)))
                 .scalars() if needs_ai_title(book)]
        preferred = [book for book in (await session.execute(select(Event).where(Event.id.in_(prefer or []))))
                     .scalars() if needs_ai_title(book)]
    order = list(dict.fromkeys([book.id for book in preferred] + [book.id for book in books]))[:limit]

    named = 0
    for book_id in order:
        outcome = await name_book(router, book_id)
        if outcome is False:
            break  # AI unavailable (or out of quota): stop here, the rest waits for the next run
        named += outcome is True
    return named
