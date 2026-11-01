"""Evidence builder: hydrate memory ids into citeable Evidence with provenance + media,
plus where the memory lives in the Memory Universe (its book and page) for "Visit memory"."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.storage import get_storage
from app.models import Conversation, Event, MediaAsset, Memory, MemoryPage, MemoryPageItem, Person, Source
from app.schemas.api import Evidence, MediaRef, SentimentOut


def make_snippet(text: str, terms: list[str], width: int = 220) -> str:
    if len(text) <= width:
        return text
    low = text.lower()
    pos = min((p for t in terms if len(t) > 2 and (p := low.find(t.lower())) >= 0), default=0)
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def sentiment_of(meta: dict | None) -> SentimentOut | None:
    """The memory's sentiment (see app/sentiment/), or None when not analysed / nothing to analyse."""
    sentiment = (meta or {}).get("sentiment") or {}
    if sentiment.get("label") not in ("positive", "negative", "neutral"):
        return None
    return SentimentOut(label=sentiment["label"], score=sentiment.get("score") or 0.0)


async def build_evidence(session: AsyncSession, user_id: uuid.UUID, ranked: list[tuple[uuid.UUID, float, list[str]]],
                         terms: list[str]) -> list[Evidence]:
    if not ranked:
        return []
    ids = [mid for mid, _, _ in ranked]
    rows = (await session.execute(
        select(Memory, Source.name, Conversation.title, Person.display_name,
               MemoryPage.id, MemoryPage.event_id, Event.title)
        .join(Source, Source.id == Memory.source_id)
        .outerjoin(Conversation, Conversation.id == Memory.conversation_id)
        .outerjoin(Person, Person.id == Memory.author_person_id)
        .outerjoin(MemoryPageItem, MemoryPageItem.memory_id == Memory.id)
        .outerjoin(MemoryPage, MemoryPage.id == MemoryPageItem.page_id)
        .outerjoin(Event, Event.id == MemoryPage.event_id)
        .where(Memory.user_id == user_id, Memory.id.in_(ids)))).all()
    by_id = {row[0].id: row for row in rows}

    media_rows = (await session.execute(select(MediaAsset).where(
        MediaAsset.user_id == user_id, MediaAsset.memory_id.in_(ids)))).scalars().all()
    storage = get_storage()
    media: dict[uuid.UUID, list[MediaRef]] = {}
    for a in media_rows:
        media.setdefault(a.memory_id, []).append(
            MediaRef(id=a.id, kind=a.kind, url=await storage.signed_url(a.object_key), mime_type=a.mime_type))

    out: list[Evidence] = []
    for mid, score, paths in ranked:
        if mid not in by_id:
            continue
        m, sname, ctitle, pname, page_id, book_id, book_title = by_id[mid]
        out.append(Evidence(
            memory_id=m.id, source_type=m.source_type, source_name=sname, conversation_id=m.conversation_id,
            conversation_title=ctitle, timestamp=m.timestamp, author=pname or m.author_raw, text=m.text,
            snippet=make_snippet(m.text, terms), language=m.language, script=m.script, score=round(score, 4),
            retrieval_paths=sorted(set(paths)), media=media.get(m.id, []), sentiment=sentiment_of(m.meta),
            book_id=book_id, book_title=book_title, page_id=page_id,
        ))
    return out
