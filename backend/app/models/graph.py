"""The knowledge graph (PLAN §12).

Relationship is a generic edge between two nodes, each addressed by (type, id), e.g.
    (PERSON, rahul) —KNOWS→ (PERSON, priya)
    (PERSON, rahul) —PART_OF→ (CONVERSATION, chat)
    (PERSON, rahul) —APPEARS_IN→ (EVENT, andhra trip)      ← added by the Memory Universe
    (EVENT, andhra trip) —RELATED_TO→ (EVENT, old trip)    ← added by the Memory Universe
Every edge records how sure we are (confidence) and who created it (parser / ai / user / universe).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_rel_src", "user_id", "src_type", "src_id"),
        Index("ix_rel_dst", "user_id", "dst_type", "dst_id"),
        Index("ix_rel_type", "user_id", "rel_type"),
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
    """An occasion such as a trip or birthday (PLAN §32). AI-inferred events are never treated as fact.

    In the Memory Universe every Event is shown as a **Memory Book** (app/universe/). A book is a
    group of Memory Pages (app/models/universe.py); everything on this row is *derived* from the
    memories on those pages and can be recomputed at any time:

        memory_count, page_count, photo_count, people   counted from the pages
        centroid                                        the average embedding of its memories
        title, summary, places                          "auto" (from names and dates) or "ai" (an LLM
                                                        read supporting_memory_ids and nothing else)
        pos_x, pos_y, pos_z                             where it floats in 3D — set once, never moved
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_start", "user_id", "start_at"),
        Index("ix_events_centroid_hnsw", "centroid", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"centroid": "vector_cosine_ops"}),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    title: Mapped[str] = mapped_column(String(500))
    occasion_type: Mapped[str] = mapped_column(String(64))  # trip | celebration | work | relationship | ... | everyday
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # For an AI-written title/summary: the exact memories the model was shown (its only source).
    supporting_memory_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[str] = mapped_column(String(64))  # "universe" | "user" | "ai:<model>"
    created_at: Mapped[datetime] = created_at()

    # ---- Memory Universe (added in migration 0003) ----
    title_source: Mapped[str] = mapped_column(String(16), default="auto")  # auto | ai | user
    summary: Mapped[str | None] = mapped_column(Text)
    places: Mapped[list] = mapped_column(JSONB, default=list)  # only places named in the memories themselves
    lane_key: Mapped[str] = mapped_column(String(100), default="")  # decides the book's angle around the time river
    pos_x: Mapped[float] = mapped_column(Float, default=0.0)
    pos_y: Mapped[float] = mapped_column(Float, default=0.0)
    pos_z: Mapped[float] = mapped_column(Float, default=0.0)
    memory_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    people: Mapped[dict] = mapped_column(JSONB, default=dict)  # {person id: messages} (the user themself excluded)
    centroid = mapped_column(Vector(get_settings().embedding_dim), nullable=True)
    centroid_count: Mapped[int] = mapped_column(Integer, default=0)  # how many embedded memories the centroid averages
    summarized_count: Mapped[int] = mapped_column(Integer, default=0)  # memory_count when the AI title was written
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at()
