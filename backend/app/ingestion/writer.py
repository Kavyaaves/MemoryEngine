"""Saving parsed records to the database as memories.

For each record: skip it if its content hash is already stored (incremental import),
otherwise normalise the text (multilingual layer), resolve the author to a Person, and
insert the Memory — in batches, because a chat export can hold 50,000+ messages.
"""

import uuid
from collections import Counter
from collections.abc import Callable

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embedding_text
from app.config import get_settings
from app.core.timeutils import make_aware
from app.ingestion.records import ParseResult, content_hashes
from app.models import Conversation, IngestionJob, Memory, MemoryParticipant, Source
from app.multilingual.tanglish import process_text
from app.people.aliases import normalize_alias
from app.people.resolver import PersonResolver

INSERT_BATCH_SIZE = 500
HASH_LOOKUP_BATCH_SIZE = 5000


async def upsert_source(session: AsyncSession, user_id: uuid.UUID, result: ParseResult) -> Source:
    """The existing Source for this chat/document, or a new one. Re-imports reuse the same row."""
    source = (await session.execute(select(Source).where(
        Source.user_id == user_id, Source.source_type == result.source_type,
        Source.fingerprint == result.fingerprint))).scalar_one_or_none()
    if source is None:
        source = Source(user_id=user_id, source_type=result.source_type, name=result.source_name[:500],
                        fingerprint=result.fingerprint, meta={"participants": result.participants, **result.meta})
        session.add(source)
        await session.flush()  # assigns source.id
    return source


async def get_or_create_conversation(session: AsyncSession, user_id: uuid.UUID, source_id: uuid.UUID,
                                     title: str | None) -> uuid.UUID | None:
    if not title:
        return None  # journals and documents are not conversations
    conversation = (await session.execute(select(Conversation).where(
        Conversation.source_id == source_id, Conversation.title == title[:500]))).scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(user_id=user_id, source_id=source_id, title=title[:500])
        session.add(conversation)
        await session.flush()
    return conversation.id


async def _already_stored(session: AsyncSession, user_id: uuid.UUID, hashes: list[str]) -> set[str]:
    stored: set[str] = set()
    for start in range(0, len(hashes), HASH_LOOKUP_BATCH_SIZE):
        rows = await session.execute(select(Memory.content_hash).where(
            Memory.user_id == user_id, Memory.content_hash.in_(hashes[start:start + HASH_LOOKUP_BATCH_SIZE])))
        stored.update(rows.scalars())
    return stored


async def insert_memories(session: AsyncSession, job: IngestionJob, source: Source, conversation_id: uuid.UUID | None,
                          result: ParseResult, resolver: PersonResolver,
                          on_progress: Callable[[float], None] = lambda fraction: None,
                          ) -> tuple[list[uuid.UUID], Counter]:
    """Insert the records that aren't stored yet. Returns (new memory ids, {total, new, skipped})."""
    records = [r for r in result.records if not r.is_system and r.text.strip()]
    hashes = content_hashes(result.fingerprint, records)
    stored = await _already_stored(session, job.user_id, hashes)
    counts = Counter(total=len(records))

    # Chat participants, and their first names so "rahul varuvaan" counts as a mention of Rahul.
    participants = {name: await resolver.resolve(name) for name in result.participants}
    first_names: dict[str, uuid.UUID] = {}
    for name, person_id in participants.items():
        first = normalize_alias(name).split()[0] if normalize_alias(name) else ""
        if len(first) >= 3:
            first_names[first] = person_id

    new_ids: list[uuid.UUID] = []
    memory_rows: list[dict] = []
    participant_rows: list[dict] = []
    for position, (record, content_hash) in enumerate(zip(records, hashes, strict=True)):
        if content_hash in stored:
            counts["skipped"] += 1
            continue
        stored.add(content_hash)

        processed = process_text(record.text)
        author_id = await resolver.resolve(record.author) if record.author else None
        memory_id = uuid.uuid4()
        meta = dict(record.meta)
        meta["embed_input"] = embedding_text(record, records[max(0, position - 2):position], processed)
        if processed.gloss_hint:
            meta["gloss_hint"] = processed.gloss_hint
        if len(processed.languages) > 1:
            meta["languages"] = processed.languages

        memory_rows.append({
            "id": memory_id, "user_id": job.user_id, "source_id": source.id, "conversation_id": conversation_id,
            "source_type": result.source_type, "source_record_id": record.record_id, "content_hash": content_hash,
            "timestamp": make_aware(record.timestamp), "author_raw": record.author[:300] if record.author else None,
            "author_person_id": author_id, "text": record.text, "normalized_text": processed.normalized,
            "transliteration": processed.transliteration, "language": processed.language,
            "script": processed.script, "search_text": processed.search_text,
            "processing_version": get_settings().processing_version, "meta": meta,
        })
        if author_id:
            participant_rows.append({"memory_id": memory_id, "person_id": author_id, "role": "author"})
        message_words = set(processed.normalized.split()) | set((processed.transliteration or "").split())
        for first_name, person_id in first_names.items():
            if person_id != author_id and first_name in message_words:
                participant_rows.append({"memory_id": memory_id, "person_id": person_id, "role": "mentioned"})

        new_ids.append(memory_id)
        counts["new"] += 1
        if len(memory_rows) >= INSERT_BATCH_SIZE:
            await _flush(session, memory_rows, participant_rows)
            on_progress((position + 1) / len(records))
            await session.commit()

    await _flush(session, memory_rows, participant_rows)
    return new_ids, counts


async def _flush(session: AsyncSession, memory_rows: list[dict], participant_rows: list[dict]) -> None:
    """Insert and clear the buffered rows."""
    if memory_rows:
        await session.execute(insert(Memory), memory_rows)
        memory_rows.clear()
    if participant_rows:
        await session.execute(pg_insert(MemoryParticipant).values(participant_rows).on_conflict_do_nothing())
        participant_rows.clear()
