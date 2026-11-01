"""The memories themselves.

A Memory is one searchable unit: a chat message, a journal entry chunk, a photo caption.
The original text is never modified (PLAN §6.1); derived columns make it searchable:

    normalized_text  lower-cased, repeated letters collapsed
    transliteration  Tamil/Malayalam script written in Latin letters
    search_text      everything above + Tanglish variants  → full-text + trigram indexes
    embedding        semantic vector                      → pgvector HNSW index
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk

EMBEDDING_DIM = get_settings().embedding_dim


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        # content_hash makes re-imports incremental: a message already stored is skipped.
        UniqueConstraint("user_id", "content_hash"),
        Index("ix_memories_user_ts", "user_id", "timestamp"),
        # "the previous time Rahul wrote" (Memory Universe connections)
        Index("ix_memories_user_author_ts", "user_id", "author_person_id", "timestamp"),
        Index("ix_memories_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_memories_search_trgm", "search_text", postgresql_using="gin",
              postgresql_ops={"search_text": "gin_trgm_ops"}),
        Index("ix_memories_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_raw: Mapped[str | None] = mapped_column(String(300))  # the name exactly as the export wrote it
    author_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), index=True)

    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    transliteration: Mapped[str | None] = mapped_column(Text)
    gloss: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))  # ta | ml | en | tanglish | manglish | mixed | unknown
    script: Mapped[str] = mapped_column(String(16))  # tamil | malayalam | latin | mixed | none
    search_text: Mapped[str] = mapped_column(Text)
    # Postgres computes this itself from search_text ('simple' = no stemming; there is no Tamil dictionary).
    search_tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True))
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)  # NULL until embedded
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    processing_version: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at()


class MemoryParticipant(Base):
    """Who is involved in a memory: its author, or someone mentioned in it."""

    __tablename__ = "memory_participants"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)  # author | mentioned


class MediaAsset(Base):
    """A photo / audio / video file. The bytes live in object storage; only the key is stored here."""

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"))
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # photo | audio | video
    object_key: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at()
