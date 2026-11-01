"""Where memories come from: a Source (one chat / one journal file), the IngestionJob that
processed an uploaded file, and the Conversation a chat message belongs to."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DUPLICATE = "duplicate"  # the exact same file was already imported


class Source(Base):
    """One logical origin of memories, e.g. a single WhatsApp chat or a journal file."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("user_id", "source_type", "fingerprint"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_type: Mapped[str] = mapped_column(String(32))  # whatsapp | instagram | journal | document | image | ...
    name: Mapped[str] = mapped_column(String(500))
    # Stable identity (e.g. hash of the chat name) so re-importing the same chat reuses this row.
    fingerprint: Mapped[str] = mapped_column(String(128))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at()
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJob(Base):
    """One uploaded file and the progress of processing it."""

    __tablename__ = "ingestion_jobs"
    # "Has this user already imported this exact file?" (duplicate upload check in api/uploads.py)
    __table_args__ = (Index("ix_ingestion_jobs_user_hash", "user_id", "file_hash"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(1000))  # where the raw upload is stored
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(200))
    options: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. {"self_name": "Maaz"}
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)  # {total, new, skipped, embedded, media}
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at()
