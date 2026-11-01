"""The ingestion job runner (PLAN §24–25). Runs in the arq worker (or in-process in dev).

    process_job(job_id)
      1. load the uploaded file from storage and parse it   (dispatch.py → parsers/)
      2. store each chat/document as memories               (writer.py)
      3. add graph edges for each conversation               (graph_builder.py)
      4. store media and describe standalone photos/audio   (media.py)
      5. embed the new memories                             (ai/embeddings.py)
      6. learn the user's Tanglish spellings                 (multilingual/personal_lexicon.py)
      7. place the new memories in the Memory Universe       (universe/updater.py)
         and give new books an AI title                      (universe/titles.py)
      8. sentiment of the new memories (local model)         (sentiment/pipeline.py)

Every step only touches *new* records, so re-uploading an updated chat export is cheap.
A failed job keeps what it stored; retrying skips those records and continues.
"""

import asyncio
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed_memories
from app.db import SessionLocal
from app.ingestion.dispatch import parse_upload
from app.ingestion.graph_builder import build_conversation_edges
from app.ingestion.media import attach_chat_media, ingest_media_file
from app.ingestion.writer import get_or_create_conversation, insert_memories, upsert_source
from app.media.storage import get_storage
from app.models import IngestionJob, JobStatus, User
from app.multilingual.personal_lexicon import learn_from_memories
from app.people.resolver import PersonResolver
from app.sentiment.pipeline import analyze_memories
from app.universe.titles import name_books
from app.universe.updater import update_universe

log = logging.getLogger(__name__)
MEDIA_SOURCE_TYPES = ("image", "audio", "video")


async def process_job(job_id: uuid.UUID | str) -> None:
    job_id = uuid.UUID(str(job_id))
    async with SessionLocal() as session:
        job = await session.get(IngestionJob, job_id)
        if job is None or job.status in (JobStatus.COMPLETED, JobStatus.DUPLICATE):
            return
        await _update_job(session, job, status=JobStatus.PROCESSING, progress=0.02, error=None)
        try:
            stats = await run_ingestion(session, job)
        except Exception as exc:
            log.exception("ingestion job %s failed", job_id)
            await session.rollback()
            job = await session.get(IngestionJob, job_id)
            await _update_job(session, job, status=JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}"[:2000])
            return
        await _update_job(session, job, status=JobStatus.COMPLETED, progress=1.0, stats=stats)


async def _update_job(session: AsyncSession, job: IngestionJob, **changes) -> None:
    for field, value in changes.items():
        setattr(job, field, value)
    await session.commit()  # commit so the Upload page (polling) sees the change


async def _self_names(session: AsyncSession, job: IngestionJob) -> set[str]:
    """Names that refer to the user themself: the name typed on upload, and their display name."""
    user = await session.get(User, job.user_id)
    names = {job.options.get("self_name"), user.display_name if user else None}
    return {name for name in names if name}


async def _update_universe_safely(session: AsyncSession, job: IngestionJob):
    """The universe is derived data: if updating it fails, the import still succeeds and the
    next update (another import, the worker's job, or `python -m app.universe`) catches up."""
    try:
        return await update_universe(session, job.user_id, job.id)
    except Exception:
        log.exception("universe update failed for job %s; it will catch up on the next run", job.id)
        await session.rollback()
        return None


async def build_universe(user_id: uuid.UUID | str) -> None:
    """Place memories imported before the universe existed (POST /api/universe/build), then name books."""
    user_id = uuid.UUID(str(user_id))
    async with SessionLocal() as session:
        stats = await update_universe(session, user_id)
    await name_books(user_id, prefer=[uuid.UUID(i) for i in stats.new_book_ids])


async def run_ingestion(session: AsyncSession, job: IngestionJob) -> dict:
    # 1. Load and parse.
    data = await get_storage().get(job.object_key)
    parsed = await asyncio.to_thread(parse_upload, job.filename, data, job.source_type)  # CPU work off the event loop

    stats: Counter = Counter()
    new_memory_ids: list[uuid.UUID] = []
    resolver = PersonResolver(session, job.user_id, await _self_names(session, job))

    # 2 + 3. Store each chat/document, then its conversation's graph edges.
    for index, result in enumerate(parsed.results):
        source = await upsert_source(session, job.user_id, result)
        job.source_id = job.source_id or source.id
        if result.records:
            conversation_id = await get_or_create_conversation(session, job.user_id, source.id,
                                                               result.conversation_title)

            def on_progress(fraction: float, index: int = index) -> None:
                job.progress = 0.05 + 0.6 * (index + fraction) / len(parsed.results)

            ids, counts = await insert_memories(session, job, source, conversation_id, result, resolver, on_progress)
            new_memory_ids += ids
            stats.update(counts)
            if conversation_id and ids:
                await build_conversation_edges(session, job.user_id, conversation_id)
        source.last_processed_at = datetime.now(UTC)
        await session.commit()

    # 4. Media.
    if job.source_type in MEDIA_SOURCE_TYPES:
        source = await upsert_source(session, job.user_id, parsed.results[0])
        for media in parsed.media:
            stats["total"] += 1
            memory_id = await ingest_media_file(session, job, source, media)
            if memory_id:
                new_memory_ids.append(memory_id)
                stats["new"] += 1
    elif parsed.media:
        stats["media"] = await attach_chat_media(session, job, parsed.media)
    await _update_job(session, job, progress=0.7, stats=dict(stats))

    # 5. Embeddings (skipped gracefully when no AI provider is available).
    stats["embedded"] = await embed_memories(session, new_memory_ids, job=job)

    # 6. Personal Tanglish dictionary.
    await learn_from_memories(session, job.user_id, new_memory_ids)
    await session.commit()

    # 7. Memory Universe: new memories join existing books or start new ones. Saved to the job
    #    right away, so the Upload and Memories pages show it before the (slow) sentiment step.
    await _update_job(session, job, progress=0.9)
    universe_stats = await _update_universe_safely(session, job)
    if universe_stats is not None:
        stats["universe"] = universe_stats.as_dict()
        await _update_job(session, job, stats=dict(stats))
        try:
            await name_books(job.user_id, prefer=[uuid.UUID(i) for i in universe_stats.new_book_ids])
        except Exception:  # titles are cosmetic; the books already have auto titles
            log.exception("naming books failed for job %s", job.id)

    # 8. Sentiment (skipped gracefully when the model isn't installed; backfill catches up).
    async def on_sentiment_progress(fraction: float) -> None:
        await _update_job(session, job, progress=0.9 + 0.09 * fraction)

    stats["sentiment"] = await analyze_memories(new_memory_ids, on_sentiment_progress)
    return dict(stats)
