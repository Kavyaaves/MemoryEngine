"""Everything about embeddings (text → vector for semantic search), in one place.

    embedding_text(...)   what text we embed for a memory (message + a little context)
    embed_memories(...)   embed new memories right after an import (best effort)
    backfill(...)         embed everything still missing, e.g. after an outage or a model change
    embed_query(...)      embed a search query (shaped like a memory by query_embedding_text)

The vectors come from OpenAI (OPENAI_EMBEDDING_MODEL, 768 dimensions to match the database
column). Memories are always findable by keyword search, embedded or not.

Run the backfill yourself (no Redis/worker needed):
    python -m app.ai.embeddings
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import AIRouter, get_router
from app.config import get_settings
from app.db import SessionLocal
from app.ingestion.records import ParsedRecord
from app.models import IngestionJob, Memory
from app.multilingual.tanglish import ProcessedText, process_text

log = logging.getLogger(__name__)
MAX_EMBEDDING_CHARS = 4000
FIRST_WAIT_SECONDS = 15  # after a failed batch (rate limit, outage); doubles each time, up to MAX_WAIT_SECONDS
MAX_WAIT_SECONDS = 120


def embedding_text(record: ParsedRecord, previous: list[ParsedRecord], processed: ProcessedText) -> str:
    """Chat messages are short ("ok da", "same"), so we embed the message together with the
    two messages before it — that context is what makes the vector meaningful."""
    lines = [f"{record.author}: {processed.normalized}" if record.author else processed.normalized]
    if processed.transliteration:
        lines.append(processed.transliteration)
    context = " | ".join(f"{p.author or ''}: {p.text[:120]}" for p in previous[-2:] if p.text)
    if context:
        lines.append(f"(context: {context})")
    return "\n".join(lines)[:MAX_EMBEDDING_CHARS]


async def _texts_to_embed(memory_ids: list[uuid.UUID]) -> list[tuple[uuid.UUID, str]]:
    """(memory id, text) pairs. meta["embed_input"] was prepared at import time (see embedding_text)."""
    async with SessionLocal() as session:
        rows = await session.execute(
            select(Memory.id, Memory.meta, Memory.normalized_text).where(Memory.id.in_(memory_ids)))
        pairs = [(memory_id, (meta or {}).get("embed_input") or text) for memory_id, meta, text in rows.all()]
    return [(memory_id, text) for memory_id, text in pairs if len(text.strip()) >= 2]


async def _save_vectors(pairs: list[tuple[uuid.UUID, list[float]]]) -> None:
    model = get_settings().embedding_model
    rows = [{"id": memory_id, "embedding": vector, "embedding_model": model} for memory_id, vector in pairs]
    async with SessionLocal() as session:
        # One bulk "UPDATE … WHERE id = …" for the whole batch. (A separate UPDATE per memory
        # costs a network round trip each — with a hosted database that was the bottleneck.)
        await session.execute(update(Memory), rows)
        await session.commit()


async def _embed_batch(memory_ids: list[uuid.UUID], user_id: uuid.UUID | None) -> int:
    """Embed one batch and save the vectors. Raises AIUnavailable (e.g. rate limited).

    Database sessions are opened only for the quick read and the quick write — never while
    waiting on the AI provider. (A connection left idle during a long wait gets closed by
    the database server, and the next use of it fails.)
    """
    inputs = await _texts_to_embed(memory_ids)
    if not inputs:
        return 0
    vectors = await get_router().embed([text for _, text in inputs], task_type="RETRIEVAL_DOCUMENT", user_id=user_id)
    ids = [memory_id for memory_id, _ in inputs]
    await _save_vectors(list(zip(ids, vectors, strict=True)))  # strict: one vector per input
    return len(inputs)


def is_permanent(error: Exception) -> bool:
    """A wrong API key or an empty billing balance won't fix itself by waiting."""
    text = str(error).lower()
    return any(sign in text for sign in ("401", "invalid_api_key", "insufficient_quota"))


async def embed_memories(session: AsyncSession, memory_ids: list[uuid.UUID], job: IngestionJob | None = None,
                         user_id: uuid.UUID | None = None) -> int:
    """Right after an import (or a caption ingest): embed the new memories. If the provider
    fails part-way, whatever is left is picked up by backfill()."""
    if not memory_ids or not get_router().available("embedding"):
        return 0
    batch_size = get_settings().embedding_batch_size
    user_id = job.user_id if job else user_id  # whose usage the embedding calls count towards
    embedded = 0
    for start in range(0, len(memory_ids), batch_size):
        try:
            embedded += await _embed_batch(memory_ids[start:start + batch_size], user_id)
        except AIUnavailable as exc:
            log.warning("embedding paused (%s); %d memories left for backfill", str(exc)[:200], len(memory_ids) - start)
            break
        if job is not None:
            job.progress = 0.7 + 0.2 * min(1.0, (start + batch_size) / len(memory_ids))  # 0.9+ is sentiment
            await session.commit()
    return embedded


def _needs_embedding(current_model: str):
    """No vector yet, or a vector from a different model (vectors from two models can't be compared)."""
    return or_(Memory.embedding.is_(None), Memory.embedding_model.is_distinct_from(current_model))


async def _count_remaining(model: str) -> int:
    async with SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(Memory).where(_needs_embedding(model)))


async def _next_batch(model: str, after_id: uuid.UUID | None, size: int) -> list[uuid.UUID]:
    """The next memories to embed, walking the table in id order — so a memory that can't be
    embedded (e.g. empty text) is passed over once instead of being picked again forever."""
    async with SessionLocal() as session:
        query = select(Memory.id).where(_needs_embedding(model))
        if after_id is not None:
            query = query.where(Memory.id > after_id)
        return list((await session.execute(query.order_by(Memory.id).limit(size))).scalars())


async def backfill(max_wait_minutes: float = 30, progress: Callable[[str], None] = log.info) -> int:
    """Embed every memory that still needs it.

    - rate limit or outage: wait and retry (15 s, 30 s, 60 s … up to 2 min)
    - wrong API key or no credit left: stop at once
    - database hiccup: wait and retry
    Gives up after `max_wait_minutes` without progress. Safe to stop and re-run at any time:
    it continues where it left off.
    """
    settings = get_settings()
    model = settings.embedding_model
    if not get_router().available("embedding"):
        progress("OPENAI_API_KEY is not set - nothing to do")
        return 0

    remaining = await _count_remaining(model)
    progress(f"{remaining} memories to embed with {model}")
    embedded, last_id = 0, None
    wait, stalled_since = FIRST_WAIT_SECONDS, None
    started = time.monotonic()
    while True:
        try:
            batch = await _next_batch(model, last_id, settings.embedding_batch_size)
            if not batch:
                progress(f"done: {embedded} memories embedded in {int(time.monotonic() - started)} s")
                return embedded
            embedded += await _embed_batch(batch, user_id=None)
        except (AIUnavailable, DBAPIError, OSError) as exc:
            if isinstance(exc, AIUnavailable) and is_permanent(exc):
                progress(f"stopping: {str(exc)[:200]} (fix the key or billing, then run again)")
                return embedded
            stalled_since = stalled_since or time.monotonic()
            if time.monotonic() - stalled_since > max_wait_minutes * 60:
                progress(f"stopping: no progress for {max_wait_minutes} min ({str(exc)[:160]}). Run again later.")
                return embedded
            reason = "embedding provider unavailable" if isinstance(exc, AIUnavailable) else "database connection problem"
            progress(f"{reason} - waiting {wait} s ({embedded}/{remaining} done)")
            await asyncio.sleep(wait)  # no database connection is held while waiting
            wait = min(wait * 2, MAX_WAIT_SECONDS)
            continue
        last_id = batch[-1]
        wait, stalled_since = FIRST_WAIT_SECONDS, None
        progress(f"{embedded}/{remaining} embedded")


def query_embedding_text(query: str) -> str:
    """The search query in the same shape as a stored memory's embedding text (see embedding_text):
    normalised, plus a Latin-letter transliteration when it contains Tamil or Malayalam script.

    Both sides of the comparison then look alike: a question typed in Tamil script also carries
    its Tanglish spelling, which is how many of the stored chat messages are written.
    """
    processed = process_text(query)
    lines = [processed.normalized]
    if processed.transliteration:
        lines.append(processed.transliteration)
    return "\n".join(lines)[:MAX_EMBEDDING_CHARS]


async def embed_query(router: AIRouter, query: str, user_id: uuid.UUID | None = None) -> list[float] | None:
    """Vector for a search query, or None when no embedding provider is reachable."""
    if not router.available("embedding"):
        return None
    try:
        vectors = await router.embed([query_embedding_text(query)], task_type="RETRIEVAL_QUERY", user_id=user_id)
    except AIUnavailable:
        return None
    return vectors[0]


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(backfill(progress=print))
