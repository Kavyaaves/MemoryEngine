"""Giving memories a sentiment, and keeping it up to date.

    analyze_memories(ids)   right after an import or a caption ingest (best effort)
    backfill()              every memory that has no sentiment yet, e.g. data imported before this existed
                            (python -m app.sentiment, the worker's cron job, or the AI Lab button)

The result is stored in memory.meta["sentiment"]:
    {"label": "positive", "score": 0.99, "model": "vishnuexe/TamilSense-model"}
label is positive | negative | neutral, or "none" when there is nothing to analyse:
    - a photo is analysed only through its ingested caption — the photo itself is never looked at;
    - a photo without a caption, or audio/video without a transcript, is just a file name → "none".
Storing "none" too means every memory is marked as done, so it isn't picked up again.

Like the embeddings, no database connection is held while the model is working.
"""

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import bindparam, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.config import get_settings
from app.db import SessionLocal
from app.models import Memory
from app.sentiment.model import SentimentUnavailable, classify

log = logging.getLogger(__name__)
MEMORIES_PER_BATCH = 256  # read, classify and save this many memories at a time
FILE_NAME_ONLY = re.compile(r"^\[(photo|image|audio|video)\] [^\n]*$")  # "[audio] note.mp3" (see ingestion/media.py)

# UPDATE memories SET meta = meta || :patch WHERE id = :memory_id
# "||" merges the patch into the existing JSON, so no other key in meta is touched.
_table = Memory.__table__
SET_SENTIMENT = (update(_table).where(_table.c.id == bindparam("memory_id"))
                 .values(meta=_table.c.meta.op("||")(bindparam("patch", type_=JSONB))))


def sentiment_text(source_type: str, text: str | None, meta: dict) -> str | None:
    """The text whose sentiment we want, or None when there is nothing to analyse."""
    if source_type == "image":
        return (meta.get("caption_ingested") or "").strip() or None  # the user's caption, never the photo
    text = (text or "").strip()
    if len(text) < 2 or FILE_NAME_ONLY.match(text):
        return None
    return text


async def _analyze_batch(memory_ids: list[uuid.UUID], model_name: str) -> int:
    """Classify one batch and save the results. Returns how many had text to analyse."""
    async with SessionLocal() as session:
        rows = (await session.execute(select(Memory.id, Memory.source_type, Memory.text, Memory.meta)
                                      .where(Memory.id.in_(memory_ids)))).all()
    texts = {memory_id: sentiment_text(source_type, text, meta or {}) for memory_id, source_type, text, meta in rows}
    to_classify = [(memory_id, text) for memory_id, text in texts.items() if text]

    # The model is slow CPU work: run it in a worker thread so the API keeps answering meanwhile.
    results = await asyncio.to_thread(classify, [text for _, text in to_classify])

    sentiments = {memory_id: {"label": "none", "score": None, "model": model_name} for memory_id in texts}
    for (memory_id, _), result in zip(to_classify, results, strict=True):
        sentiments[memory_id] = {"label": result.label, "score": result.score, "model": model_name}
    if sentiments:
        async with SessionLocal() as session:
            await session.execute(SET_SENTIMENT, [{"memory_id": memory_id, "patch": {"sentiment": sentiment}}
                                                  for memory_id, sentiment in sentiments.items()])
            await session.commit()
    return len(to_classify)


async def analyze_memories(memory_ids: list[uuid.UUID],
                           on_progress: Callable[[float], Awaitable[None]] | None = None) -> int:
    """Analyse these memories. Best effort: returns 0 when sentiment is switched off or the model
    can't be loaded — backfill() catches up later."""
    settings = get_settings()
    if not settings.sentiment_enabled or not memory_ids:
        return 0
    analyzed = 0
    for start in range(0, len(memory_ids), MEMORIES_PER_BATCH):
        try:
            analyzed += await _analyze_batch(memory_ids[start:start + MEMORIES_PER_BATCH], settings.sentiment_model)
        except SentimentUnavailable as exc:
            log.warning("sentiment skipped (%s); run `python -m app.sentiment` later", exc)
            break
        if on_progress:
            await on_progress(min(1.0, (start + MEMORIES_PER_BATCH) / len(memory_ids)))
    return analyzed


def needs_sentiment(model_name: str):
    """SQL condition: no sentiment yet, or one from a different model."""
    return or_(~Memory.meta.has_key("sentiment"),
               Memory.meta[("sentiment", "model")].astext.is_distinct_from(model_name))


async def count_status(user_id: uuid.UUID | None = None) -> dict:
    """{"done": …, "remaining": …} memories, for one user or everyone."""
    model_name = get_settings().sentiment_model
    async with SessionLocal() as session:
        query = select(func.count()).select_from(Memory)
        if user_id:
            query = query.where(Memory.user_id == user_id)
        total = await session.scalar(query)
        remaining = await session.scalar(query.where(needs_sentiment(model_name)))
    return {"done": total - remaining, "remaining": remaining}


async def backfill(user_id: uuid.UUID | None = None, progress: Callable[[str], None] = log.info) -> int:
    """Analyse every memory that still needs it (one user's, or everyone's). Safe to stop and re-run:
    it continues where it left off. Returns how many memories were analysed."""
    settings = get_settings()
    if not settings.sentiment_enabled:
        progress("sentiment is switched off (SENTIMENT_ENABLED=false)")
        return 0
    remaining = (await count_status(user_id))["remaining"]
    progress(f"{remaining} memories to analyse with {settings.sentiment_model}")

    analyzed, last_id = 0, None
    while True:
        # Walk the table in id order, like the embedding backfill does.
        query = select(Memory.id).where(needs_sentiment(settings.sentiment_model))
        if user_id:
            query = query.where(Memory.user_id == user_id)
        if last_id is not None:
            query = query.where(Memory.id > last_id)
        async with SessionLocal() as session:
            batch = list((await session.execute(query.order_by(Memory.id).limit(MEMORIES_PER_BATCH))).scalars())
        if not batch:
            progress(f"done: {analyzed} memories analysed")
            return analyzed
        try:
            analyzed += await _analyze_batch(batch, settings.sentiment_model)
        except SentimentUnavailable as exc:
            progress(f"stopping: {exc}")
            return analyzed
        last_id = batch[-1]
        progress(f"{analyzed}/{remaining} analysed")
