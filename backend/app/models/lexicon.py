import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.columns import uuid_pk


class LexiconEntry(Base):
    """Personal Tanglish dictionary (PLAN §7): a spelling and the word it stands for.

    Rows with user_id NULL are the global seed list; user rows are spellings learned from
    that user's own chats (with how often they were seen). This table is also the raw
    material for the Tanglish-normaliser fine-tuning experiment (PLAN §20A).
    """

    __tablename__ = "lexicon_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "surface_form", "canonical_form", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    surface_form: Mapped[str] = mapped_column(String(200), index=True)  # e.g. "seriii"
    canonical_form: Mapped[str] = mapped_column(String(200), index=True)  # e.g. "seri"
    language: Mapped[str] = mapped_column(String(16))
    gloss: Mapped[str | None] = mapped_column(String(300))  # e.g. "okay"
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(32), default="seed")  # seed | corpus | user
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
