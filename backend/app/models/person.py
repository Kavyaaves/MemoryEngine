"""People and the names they appear under (PLAN §13 entity resolution).

"Rahul", "Rahul ❤\ufe0f" and "rahul" are the same Person with several PersonAlias rows.
Uncertain matches ("R" → Rahul?) are stored as SUGGESTED aliases until the user answers.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.columns import created_at, user_fk, uuid_pk


class AliasStatus(StrEnum):
    CONFIRMED = "confirmed"  # exact match or verified by the user
    SUGGESTED = "suggested"  # fuzzy match waiting for "Is R the same as Rahul?"
    UNSURE = "unsure"  # user answered "not sure"
    REJECTED = "rejected"  # user answered "no"


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    display_name: Mapped[str] = mapped_column(String(300))
    is_self: Mapped[bool] = mapped_column(Boolean, default=False)  # the user themself in their own chats
    created_at: Mapped[datetime] = created_at()
    aliases: Mapped[list["PersonAlias"]] = relationship(back_populates="person", lazy="selectin")


class PersonAlias(Base):
    __tablename__ = "person_aliases"
    # A name is CONFIRMED for one person, but may also be SUGGESTED for other people.
    __table_args__ = (UniqueConstraint("user_id", "alias", "person_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(300))  # as written, e.g. "Rahul ❤\ufe0f"
    normalized_alias: Mapped[str] = mapped_column(String(300), index=True)  # e.g. "rahul"
    status: Mapped[str] = mapped_column(String(16), default=AliasStatus.CONFIRMED)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    person: Mapped[Person] = relationship(back_populates="aliases")
