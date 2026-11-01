"""Imported sources (one per chat / document) and source-level deletion (PLAN §4.1, §39).

    GET    /api/sources
    DELETE /api/sources/{id}   deletes the source and everything derived from it
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.db import get_session
from app.ingestion.graph_builder import conversation_edge_creator
from app.media.storage import get_storage
from app.models import AuditLog, Conversation, IngestionJob, MediaAsset, Memory, Relationship, Source, User
from app.schemas.api import SourceOut
from app.universe.updater import prune_universe

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
async def list_sources(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    memory_counts = (select(Memory.source_id, func.count().label("n")).where(Memory.user_id == user.id)
                     .group_by(Memory.source_id).subquery())
    rows = await session.execute(
        select(Source, func.coalesce(memory_counts.c.n, 0))
        .outerjoin(memory_counts, memory_counts.c.source_id == Source.id)
        .where(Source.user_id == user.id).order_by(Source.created_at.desc()))
    return [SourceOut(id=source.id, source_type=source.source_type, name=source.name, memory_count=count,
                      created_at=source.created_at, last_processed_at=source.last_processed_at)
            for source, count in rows.all()]


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: uuid.UUID, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    source = await session.get(Source, source_id)
    if source is None or source.user_id != user.id:
        raise HTTPException(404, "source not found")

    # Remember which stored files to delete once the rows are gone.
    media_keys = (await session.execute(select(MediaAsset.object_key).where(MediaAsset.source_id == source_id))).scalars()
    upload_keys = (await session.execute(select(IngestionJob.object_key).where(
        IngestionJob.source_id == source_id))).scalars()
    object_keys = [*media_keys, *upload_keys]

    # Conversation-level graph edges have no foreign key to a memory, so delete them explicitly.
    conversation_ids = (await session.execute(select(Conversation.id).where(
        Conversation.source_id == source_id))).scalars().all()
    if conversation_ids:
        await session.execute(delete(Relationship).where(
            Relationship.user_id == user.id,
            Relationship.created_by.in_([conversation_edge_creator(c) for c in conversation_ids])))
    await session.execute(delete(IngestionJob).where(IngestionJob.source_id == source_id))
    await session.delete(source)  # ON DELETE CASCADE removes memories, participants, media rows
    session.add(AuditLog(user_id=user.id, action="delete_source", target=str(source_id), detail={"name": source.name}))
    await session.commit()
    # The universe's pages and books were derived from those memories: recount them, drop empty ones.
    await prune_universe(session, user.id)

    storage = get_storage()
    for key in object_keys:
        try:
            await storage.delete(key)
        except Exception:
            pass
    return Response(status_code=204)
