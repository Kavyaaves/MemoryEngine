"""Photos: only their METADATA is used — the picture itself is never looked at (strict).

On upload a photo becomes one memory, built only from:
    - its file name                       "IMG_20240614_183012.jpg"
    - when it was taken                   EXIF "DateTimeOriginal" (read from the file header)
    - when it was last changed            EXIF "DateTime", and the file's "last modified" time sent by the browser
The pixels are never decoded and the photo is never sent to an AI model.
The memory always gets a date, so every photo appears in the timeline next to the other memories.

The user can then write a caption for each photo (Media page). A caption is only a draft until the
user clicks "Ingest Captions": ingest_captions() then makes the caption the memory's searchable text.

    meta["caption"]           the caption the user typed (draft)
    meta["caption_ingested"]  the caption that was last ingested
    → a caption is "pending" while these two differ.
"""

import io
import uuid
from datetime import UTC, datetime

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import MAX_EMBEDDING_CHARS, embed_memories
from app.core.timeutils import make_aware
from app.models import Memory
from app.multilingual.tanglish import process_text
from app.sentiment.pipeline import analyze_memories

# EXIF tag numbers (see the EXIF standard).
EXIF_DATETIME = 0x0132  # "DateTime": when the file was last changed
EXIF_SUB_IFD = 0x8769  # the EXIF sub-block that holds the camera details
EXIF_DATETIME_ORIGINAL = 0x9003  # "DateTimeOriginal": when the photo was taken

# Where a photo's timeline date came from, best first.
DATE_SOURCES = ("exif_taken", "filename", "exif_changed", "file_modified", "uploaded")


def _parse_exif_date(value) -> datetime | None:
    """EXIF writes dates as "2024:06:14 18:30:12" (local time, no timezone)."""
    try:
        return datetime.strptime(str(value).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def read_exif_dates(data: bytes) -> tuple[datetime | None, datetime | None]:
    """(taken, changed) from the EXIF header, or None for each date that isn't there.

    Image.open() only reads the file header; the pixels are never decoded.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            taken = exif.get_ifd(EXIF_SUB_IFD).get(EXIF_DATETIME_ORIGINAL)
            changed = exif.get(EXIF_DATETIME)
    except Exception:  # a broken file, or a format Pillow can't open (e.g. HEIC): no EXIF dates
        return None, None
    return _parse_exif_date(taken) if taken else None, _parse_exif_date(changed) if changed else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def photo_metadata(filename: str, data: bytes, filename_date: datetime | None,
                   file_modified_at: datetime | None) -> tuple[datetime, dict]:
    """(the photo's timeline date, the metadata stored in memory.meta)."""
    taken, changed = read_exif_dates(data)
    candidates = {
        "exif_taken": make_aware(taken),
        "filename": make_aware(filename_date),
        "exif_changed": make_aware(changed),
        "file_modified": file_modified_at,
        "uploaded": datetime.now(UTC),  # nothing else known: the day it was uploaded
    }
    date_source = next(source for source in DATE_SOURCES if candidates[source] is not None)
    meta = {
        "filename": filename,
        "taken_at": _iso(candidates["exif_taken"]),
        "changed_at": _iso(candidates["exif_changed"]),
        "file_modified_at": _iso(file_modified_at),
        "date_source": date_source,
    }
    return candidates[date_source], meta


def photo_text(filename: str, caption: str = "") -> str:
    """The searchable text of a photo memory: the caption (once ingested) and the file name."""
    return f"{caption}\n[photo] {filename}" if caption else f"[photo] {filename}"


def caption_status(meta: dict) -> str:
    """none | pending | ingested"""
    caption = meta.get("caption") or ""
    if caption != (meta.get("caption_ingested") or ""):
        return "pending"
    return "ingested" if caption else "none"


def is_pending_caption():
    """SQL condition: the photo's caption was changed since it was last ingested."""
    return (func.coalesce(Memory.meta["caption"].astext, "")
            != func.coalesce(Memory.meta["caption_ingested"].astext, ""))


async def ingest_captions(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Make every pending caption the searchable text of its photo, then embed and analyse those photos."""
    photos = (await session.execute(select(Memory).where(
        Memory.user_id == user_id, Memory.source_type == "image", is_pending_caption()))).scalars().all()

    for memory in photos:
        caption = (memory.meta.get("caption") or "").strip()
        text = photo_text(memory.meta.get("filename") or "photo", caption)
        processed = process_text(text)
        memory.text = text
        memory.normalized_text = processed.normalized
        memory.transliteration = processed.transliteration
        memory.language = processed.language
        memory.script = processed.script
        memory.search_text = processed.search_text
        memory.embedding = None  # the old vector describes the old text
        memory.embedding_model = None
        # A new dict (not an in-place change), so SQLAlchemy notices the JSONB column changed.
        memory.meta = {**memory.meta, "caption_ingested": caption, "embed_input": text[:MAX_EMBEDDING_CHARS]}
    await session.commit()

    ids = [memory.id for memory in photos]
    embedded = await embed_memories(session, ids, user_id=user_id)
    analyzed = await analyze_memories(ids)  # the caption's sentiment (a cleared caption → "none")
    return {"ingested": len(ids), "embedded": embedded, "sentiment": analyzed}
