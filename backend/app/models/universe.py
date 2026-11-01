"""Tables behind the Memory Universe (app/universe/): pages, which memory is on which page, and a change feed.

    Memory Book  (models/graph.py Event)   an event / period, e.g. "Andhra Trip"
      └─ MemoryPage                         one conversation (or your photos) on one day
           └─ MemoryPageItem                one original memory on that page

All of it is *derived*: the memories table is never changed. Deleting every row here and
running the universe update again rebuilds the same pages (page keys are deterministic).

UniverseChange is an append-only log of what each update did ("book created", "book grew",
"new connection"). The Memories page reads it to show "New memories discovered" and to know
that it should refresh — without reloading the page or moving the camera.
"""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk


class MemoryPage(Base):
    """All memories of one thread on one local calendar day.

    thread_key is the conversation id (chats), the source id (journals, documents) or "media"
    (photos, audio and video: each uploaded file is its own source, so they are grouped by day).
    """

    __tablename__ = "memory_pages"
    __table_args__ = (
        UniqueConstraint("user_id", "page_key"),
        Index("ix_memory_pages_event", "user_id", "event_id", "start_at"),
        Index("ix_memory_pages_day", "user_id", "day"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    # NULL only for a moment: between creating the page and choosing its book in the same transaction.
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    page_key: Mapped[str] = mapped_column(String(200))  # "<thread_key>:<YYYY-MM-DD>"
    thread_key: Mapped[str] = mapped_column(String(64))
    day: Mapped[date] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    memory_count: Mapped[int] = mapped_column(Integer, default=0)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    people: Mapped[dict] = mapped_column(JSONB, default=dict)  # {person id: messages} (the user themself excluded)
    centroid = mapped_column(Vector(get_settings().embedding_dim), nullable=True)
    centroid_count: Mapped[int] = mapped_column(Integer, default=0)
    preview: Mapped[str] = mapped_column(Text, default="")  # the first line of the page, for lists
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class MemoryPageItem(Base):
    """Which page a memory is on. A memory without a row here has not been placed yet —
    that is how the universe update finds the new memories after an import."""

    __tablename__ = "memory_page_items"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_pages.id", ondelete="CASCADE"), index=True)


class UniverseChange(Base):
    """One thing a universe update changed. `id` only ever grows, so it doubles as a cursor:
    "give me every change after 1234"."""

    __tablename__ = "universe_changes"
    __table_args__ = (Index("ix_universe_changes_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the ingestion job, if any
    kind: Mapped[str] = mapped_column(String(32))  # book_created | book_grown | book_renamed | book_removed | connection
    entity_type: Mapped[str] = mapped_column(String(16))  # EVENT | PERSON
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at()
