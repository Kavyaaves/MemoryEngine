"""The knowledge graph (PLAN §12).

Relationship is a generic edge between two nodes, each addressed by (type, id), e.g.
    (PERSON, rahul) —KNOWS→ (PERSON, priya)
    (PERSON, rahul) —PART_OF→ (CONVERSATION, chat)
Every edge records how sure we are (confidence) and who created it (parser / ai / user).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_rel_src", "user_id", "src_type", "src_id"),
        Index("ix_rel_dst", "user_id", "dst_type", "dst_id"),
        # NULLS NOT DISTINCT: edges without a source memory are still de-duplicated.
        UniqueConstraint("user_id", "src_type", "src_id", "rel_type", "dst_type", "dst_id", "source_memory_id",
                         postgresql_nulls_not_distinct=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    src_type: Mapped[str] = mapped_column(String(32))  # PERSON | CONVERSATION | EVENT | PLACE | MEMORY
    src_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rel_type: Mapped[str] = mapped_column(String(32))  # KNOWS | PART_OF | MENTIONED | TRAVELLED_WITH | ...
    dst_type: Mapped[str] = mapped_column(String(32))
    dst_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(String(64))  # "parser:conv:<id>" | "ai:<model>" | "user"
    created_at: Mapped[datetime] = created_at()


class Event(Base):
    """An occasion such as a trip or birthday (PLAN §32). AI-inferred events are never treated as fact."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    title: Mapped[str] = mapped_column(String(500))
    occasion_type: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    supporting_memory_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at()


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at()
