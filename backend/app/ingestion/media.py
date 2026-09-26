"""Photos, audio and video (PLAN §17–19).

Two cases:
- media inside a chat export (WhatsApp zip): store the file and link it to the message
  that says "<attached: IMG-...jpg>";
- a media file uploaded on its own: store it and create a memory for it —
  photos: metadata only (name + dates, see photos.py) — the picture is never sent to an AI model;
  audio: a transcript (OpenAI, see ai/providers/router.py);
  video: stored and findable by file name only (analysis is V2).
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import get_router
from app.config import get_settings
from app.core.timeutils import make_aware
from app.ingestion.dispatch import MediaFile
from app.ingestion.photos import photo_metadata, photo_text
from app.ingestion.records import sha256_hex
from app.media.storage import get_storage, object_key
from app.models import IngestionJob, MediaAsset, Memory, Source
from app.multilingual.tanglish import process_text

STORAGE_FOLDERS = {"photo": "photos", "audio": "audio", "video": "video"}
FILENAME_DATE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")  # IMG-20240614-WA0001.jpg


def date_from_filename(name: str) -> datetime | None:
    match = FILENAME_DATE.search(name)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None


async def _store(job: IngestionJob, media: MediaFile) -> tuple[str, str]:
    """Upload the bytes to object storage; returns (sha256, object key)."""
    sha = sha256_hex(media.data)
    key = object_key(job.user_id, STORAGE_FOLDERS.get(media.kind, "media"), sha, media.name)
    await get_storage().put(key, media.data, media.mime_type)
    return sha, key


async def attach_chat_media(session: AsyncSession, job: IngestionJob, media_files: list[MediaFile]) -> int:
    """Store media from a chat export, linked to the message that references each file."""
    names = [m.name for m in media_files]
    rows = await session.execute(select(Memory.id, Memory.meta).where(
        Memory.user_id == job.user_id, Memory.source_id == job.source_id, Memory.meta["media"].astext.in_(names)))
    memory_by_filename = {meta.get("media"): memory_id for memory_id, meta in rows.all()}

    for media in media_files:
        sha, key = await _store(job, media)
        session.add(MediaAsset(user_id=job.user_id, source_id=job.source_id, memory_id=memory_by_filename.get(media.name),
                               kind=media.kind, object_key=key, mime_type=media.mime_type,
                               size_bytes=len(media.data), sha256=sha, meta={"filename": media.name}))
    return len(media_files)


async def describe_media(media: MediaFile, user_id: uuid.UUID) -> tuple[str, dict]:
    """Audio and video only: (text to index, extra metadata). Falls back to the file name when AI is unavailable.
    Photos never come here — see describe_photo."""
    meta: dict = {"filename": media.name}
    text = ""
    try:
        if media.kind == "audio":
            transcript = await get_router().transcribe(media.data, media.name, user_id=user_id)
            meta["transcript_segments"] = transcript.segments
            meta["transcript_provider"] = f"{transcript.provider}:{transcript.model}"
            text = transcript.text
        elif media.kind == "video":
            meta["pending"] = "video analysis is planned for V2"
    except AIUnavailable as exc:
        meta["ai_pending"] = str(exc)[:500]  # can be described later
    return text.strip() or f"[{media.kind}] {media.name}", meta


def describe_photo(media: MediaFile, job: IngestionJob) -> tuple[str, datetime, dict]:
    """(text to index, timeline date, metadata) from the photo's name and dates only — no AI."""
    modified_ms = job.options.get("file_modified_ms")  # the file's "last modified" time, sent by the browser
    file_modified_at = datetime.fromtimestamp(modified_ms / 1000, UTC) if modified_ms else None
    timestamp, meta = photo_metadata(media.name, media.data, date_from_filename(media.name), file_modified_at)
    return photo_text(media.name), timestamp, meta


async def ingest_media_file(session: AsyncSession, job: IngestionJob, source: Source,
                            media: MediaFile) -> uuid.UUID | None:
    """One uploaded photo/audio/video → one memory. Returns None if it was already imported."""
    content_hash = sha256_hex("media", sha256_hex(media.data))
    already_stored = await session.execute(select(Memory.id).where(
        Memory.user_id == job.user_id, Memory.content_hash == content_hash))
    if already_stored.first():
        return None

    if job.source_type == "image":  # a photo: metadata only, never AI
        text, timestamp, meta = describe_photo(media, job)
    else:
        text, meta = await describe_media(media, job.user_id)
        timestamp = make_aware(date_from_filename(media.name))
    meta["embed_input"] = text[:4000]
    processed = process_text(text)
    memory = Memory(user_id=job.user_id, source_id=source.id, source_type=job.source_type,
                    content_hash=content_hash, timestamp=timestamp,
                    text=text, normalized_text=processed.normalized, transliteration=processed.transliteration,
                    language=processed.language, script=processed.script, search_text=processed.search_text,
                    processing_version=get_settings().processing_version, meta=meta)
    session.add(memory)
    await session.flush()

    sha, key = await _store(job, media)
    session.add(MediaAsset(user_id=job.user_id, source_id=source.id, memory_id=memory.id, kind=media.kind,
                           object_key=key, mime_type=media.mime_type, size_bytes=len(media.data), sha256=sha,
                           meta={"filename": media.name}))
    await session.commit()
    return memory.id
