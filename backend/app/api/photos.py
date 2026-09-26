"""The photo library: browse and filter photos by their metadata, and caption them.

    GET  /api/photos?start=&end=&q=&caption=     photos, newest first (filters are optional)
    PUT  /api/photos/{memory_id}/caption         save a caption (a draft until it is ingested)
    POST /api/photos/captions/ingest             make every pending caption searchable

Photos are never analysed — see ingestion/photos.py.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.core.timeutils import end_of_day, start_of_day
from app.db import get_session
from app.ingestion.photos import caption_status, ingest_captions, is_pending_caption
from app.media.storage import get_storage
from app.models import AuditLog, MediaAsset, Memory, User
from app.schemas.api import CaptionIn, CaptionIngestOut, PhotoOut, PhotosOut

router = APIRouter(prefix="/photos", tags=["photos"])
CAPTION_FILTERS = {"all", "none", "pending", "ingested"}


def _photo_out(memory: Memory, media: MediaAsset, url: str) -> PhotoOut:
    meta = memory.meta or {}
    return PhotoOut(
        memory_id=memory.id, filename=meta.get("filename") or media.meta.get("filename") or "photo", url=url,
        mime_type=media.mime_type, timestamp=memory.timestamp, date_source=meta.get("date_source") or "filename",
        taken_at=meta.get("taken_at"), changed_at=meta.get("changed_at"), file_modified_at=meta.get("file_modified_at"),
        uploaded_at=memory.created_at, caption=meta.get("caption") or "", caption_status=caption_status(meta))


@router.get("", response_model=PhotosOut)
async def list_photos(start: date | None = None, end: date | None = None,
                      q: str | None = Query(None, description="text in the file name or caption"),
                      caption: str = Query("all", description="all | none | pending | ingested"),
                      limit: int = Query(200, ge=1, le=1000),
                      user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if caption not in CAPTION_FILTERS:
        raise HTTPException(422, f"caption must be one of {sorted(CAPTION_FILTERS)}")
    is_own_photo = (Memory.user_id == user.id) & (Memory.source_type == "image")

    query = select(Memory, MediaAsset).join(MediaAsset, MediaAsset.memory_id == Memory.id).where(is_own_photo)
    if start:
        query = query.where(Memory.timestamp >= start_of_day(start))
    if end:
        query = query.where(Memory.timestamp < end_of_day(end))
    if q and q.strip():
        text = q.strip()
        query = query.where(Memory.meta["filename"].astext.icontains(text, autoescape=True)
                            | Memory.meta["caption"].astext.icontains(text, autoescape=True))

    caption_text = func.coalesce(Memory.meta["caption"].astext, "")
    if caption == "none":
        query = query.where(caption_text == "")
    elif caption == "pending":
        query = query.where(is_pending_caption())
    elif caption == "ingested":
        query = query.where(caption_text != "", ~is_pending_caption())

    rows = (await session.execute(
        query.order_by(Memory.timestamp.desc().nulls_last(), Memory.created_at.desc()).limit(limit))).all()
    pending = await session.scalar(select(func.count()).select_from(Memory).where(is_own_photo, is_pending_caption()))

    storage = get_storage()
    photos = [_photo_out(memory, media, await storage.signed_url(media.object_key)) for memory, media in rows]
    return PhotosOut(photos=photos, pending_captions=pending or 0)


@router.put("/{memory_id}/caption", response_model=PhotoOut)
async def save_caption(memory_id: uuid.UUID, body: CaptionIn, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    """Only stores the caption. It becomes searchable when the user clicks "Ingest Captions"."""
    row = (await session.execute(select(Memory, MediaAsset).join(MediaAsset, MediaAsset.memory_id == Memory.id).where(
        Memory.id == memory_id, Memory.user_id == user.id, Memory.source_type == "image"))).first()
    if row is None:  # someone else's photo looks exactly like a missing one
        raise HTTPException(404, "photo not found")
    memory, media = row
    memory.meta = {**memory.meta, "caption": body.caption.strip()}  # a new dict, so SQLAlchemy saves the change
    await session.commit()
    return _photo_out(memory, media, await get_storage().signed_url(media.object_key))


@router.post("/captions/ingest", response_model=CaptionIngestOut)
async def ingest_pending_captions(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    result = await ingest_captions(session, user.id)
    session.add(AuditLog(user_id=user.id, action="ingest_captions", detail=result))
    await session.commit()
    return CaptionIngestOut(**result)
