"""Turning names in chats into Person rows, and merging people the user says are the same.

Rule: names are merged automatically only when they normalise to the same text
("Rahul ❤\ufe0f" == "rahul"). Anything weaker ("R", "Rahu") creates a separate person plus a
SUGGESTED alias, which the People page shows as "Is R the same as Rahul? [Yes] [No]".
"""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AliasStatus, Memory, MemoryParticipant, Person, PersonAlias, Relationship
from app.people.aliases import best_matches, normalize_alias


class PersonResolver:
    """Resolves author names during one ingestion run (caches the user's known aliases)."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID, self_names: set[str] | None = None):
        self.session = session
        self.user_id = user_id
        self.self_names = {normalize_alias(n) for n in (self_names or set()) if n}
        self._known: dict[str, uuid.UUID] | None = None  # normalised alias → person id

    async def _known_aliases(self) -> dict[str, uuid.UUID]:
        if self._known is None:
            rows = await self.session.execute(
                select(PersonAlias.normalized_alias, PersonAlias.person_id)
                .where(PersonAlias.user_id == self.user_id, PersonAlias.status == AliasStatus.CONFIRMED))
            self._known = dict(rows.all())
        return self._known

    async def resolve(self, raw_name: str) -> uuid.UUID:
        """Person id for a name as it appears in an export, creating the person if needed."""
        known = await self._known_aliases()
        normalized = normalize_alias(raw_name) or raw_name.strip().casefold()
        if normalized in known:
            return known[normalized]

        person = Person(user_id=self.user_id, display_name=raw_name.strip()[:300],
                        is_self=normalized in self.self_names)
        self.session.add(person)
        await self.session.flush()  # assigns person.id
        self.session.add(PersonAlias(user_id=self.user_id, person_id=person.id, alias=raw_name[:300],
                                     normalized_alias=normalized, status=AliasStatus.CONFIRMED))
        # Similar existing names become questions for the user, never silent merges.
        for candidate_id, score in best_matches(raw_name, known):
            self.session.add(PersonAlias(user_id=self.user_id, person_id=candidate_id, alias=raw_name[:300],
                                         normalized_alias=normalized, status=AliasStatus.SUGGESTED,
                                         confidence=score))
        known[normalized] = person.id
        return person.id


async def merge_people(session: AsyncSession, user_id: uuid.UUID, keep_id: uuid.UUID, drop_id: uuid.UUID) -> None:
    """The user confirmed two people are one: move everything from `drop` to `keep`, then delete `drop`."""
    if keep_id == drop_id:
        return

    # 1. Messages they wrote.
    await session.execute(update(Memory).where(Memory.user_id == user_id, Memory.author_person_id == drop_id)
                          .values(author_person_id=keep_id))

    # 2. Participation rows (skip ones `keep` already has, to avoid duplicate primary keys).
    already_linked = select(MemoryParticipant.memory_id).where(MemoryParticipant.person_id == keep_id)
    await session.execute(delete(MemoryParticipant).where(MemoryParticipant.person_id == drop_id,
                                                          MemoryParticipant.memory_id.in_(already_linked)))
    await session.execute(update(MemoryParticipant).where(MemoryParticipant.person_id == drop_id)
                          .values(person_id=keep_id))

    # 3. Graph edges on either end.
    await session.execute(update(Relationship).where(
        Relationship.user_id == user_id, Relationship.src_type == "PERSON", Relationship.src_id == drop_id)
        .values(src_id=keep_id))
    await session.execute(update(Relationship).where(
        Relationship.user_id == user_id, Relationship.dst_type == "PERSON", Relationship.dst_id == drop_id)
        .values(dst_id=keep_id))

    # 4. Names: every alias of `drop` becomes a confirmed alias of `keep`.
    drop_aliases = (await session.execute(select(PersonAlias).where(PersonAlias.person_id == drop_id))).scalars().all()
    keep_alias_names = set((await session.execute(
        select(PersonAlias.alias).where(PersonAlias.person_id == keep_id))).scalars())
    for alias in drop_aliases:
        if alias.alias in keep_alias_names:
            await session.delete(alias)  # `keep` already has this name (e.g. as a suggestion)
        else:
            alias.person_id = keep_id
            alias.status = AliasStatus.CONFIRMED
    await session.execute(update(PersonAlias).where(
        PersonAlias.person_id == keep_id, PersonAlias.alias.in_([a.alias for a in drop_aliases]))
        .values(status=AliasStatus.CONFIRMED, confidence=1.0))

    await session.execute(delete(Person).where(Person.id == drop_id, Person.user_id == user_id))
