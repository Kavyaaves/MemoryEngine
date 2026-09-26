"""People and the "is X the same as Y?" questions (PLAN §29, §35).

    GET  /api/people
    GET  /api/people/alias-suggestions     open questions for the user
    POST /api/people/alias-feedback        the user's answer: yes (merge) / no / unsure
    GET  /api/people/{id}                  one person: timeline, conversations, related people
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.core.timeutils import local_period
from app.db import get_session
from app.models import AliasStatus, AuditLog, Conversation, Memory, MemoryParticipant, Person, PersonAlias, User
from app.people.resolver import merge_people
from app.retrieval.graph import related_people
from app.schemas.api import (
    AliasFeedbackIn,
    AliasSuggestionOut,
    ConversationRef,
    PeriodCount,
    PersonDetailOut,
    PersonOut,
    RelatedPerson,
)

router = APIRouter(prefix="/people", tags=["people"])


async def _message_stats(session: AsyncSession, user_id: uuid.UUID,
                         person_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, tuple]:
    """person id → (messages written, first seen, last seen)."""
    query = (select(Memory.author_person_id, func.count(), func.min(Memory.timestamp), func.max(Memory.timestamp))
             .where(Memory.user_id == user_id, Memory.author_person_id.is_not(None))
             .group_by(Memory.author_person_id))
    if person_ids:
        query = query.where(Memory.author_person_id.in_(person_ids))
    rows = await session.execute(query)
    return {person_id: (count, first, last) for person_id, count, first, last in rows.all()}


def _person_out(person: Person, stats: dict) -> PersonOut:
    count, first_seen, last_seen = stats.get(person.id, (0, None, None))
    aliases = sorted({a.alias for a in person.aliases if a.status == AliasStatus.CONFIRMED})
    return PersonOut(id=person.id, display_name=person.display_name, aliases=aliases, memory_count=count,
                     first_seen=first_seen, last_seen=last_seen)


@router.get("", response_model=list[PersonOut])
async def list_people(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    people = (await session.execute(select(Person).where(Person.user_id == user.id,
                                                         Person.is_self.is_(False)))).scalars().all()
    stats = await _message_stats(session, user.id)
    return sorted((_person_out(p, stats) for p in people), key=lambda p: p.memory_count, reverse=True)


@router.get("/alias-suggestions", response_model=list[AliasSuggestionOut])
async def alias_suggestions(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(PersonAlias, Person.display_name).join(Person, Person.id == PersonAlias.person_id)
        .where(PersonAlias.user_id == user.id, PersonAlias.status.in_([AliasStatus.SUGGESTED, AliasStatus.UNSURE]))
        .order_by(PersonAlias.status, PersonAlias.confidence.desc()).limit(20))
    return [AliasSuggestionOut(alias_id=alias.id, alias=alias.alias, person_id=alias.person_id, person_name=name,
                               similarity=alias.confidence) for alias, name in rows.all()]


@router.post("/alias-feedback")
async def alias_feedback(body: AliasFeedbackIn, user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    """'Is "R" the same person as Rahul?' — "yes" merges the two people."""
    suggestion = await session.get(PersonAlias, body.alias_id)
    if suggestion is None or suggestion.user_id != user.id or suggestion.person_id != body.person_id:
        raise HTTPException(404, "suggestion not found")

    if body.answer == "yes":
        # The person that currently owns this name ("R") gets merged into the suggested one (Rahul).
        current_owner = (await session.execute(select(PersonAlias.person_id).where(
            PersonAlias.user_id == user.id, PersonAlias.alias == suggestion.alias,
            PersonAlias.status == AliasStatus.CONFIRMED, PersonAlias.person_id != body.person_id))).scalar_one_or_none()
        if current_owner:
            await merge_people(session, user.id, keep_id=body.person_id, drop_id=current_owner)
        else:
            suggestion.status, suggestion.confidence = AliasStatus.CONFIRMED, 1.0
    elif body.answer == "no":
        suggestion.status = AliasStatus.REJECTED
    else:
        suggestion.status = AliasStatus.UNSURE

    session.add(AuditLog(user_id=user.id, action="alias_feedback", target=str(body.alias_id),
                         detail={"answer": body.answer, "alias": suggestion.alias}))
    await session.commit()
    return {"ok": True}


@router.get("/{person_id}", response_model=PersonDetailOut)
async def person_detail(person_id: uuid.UUID, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    person = await session.get(Person, person_id)
    if person is None or person.user_id != user.id:
        raise HTTPException(404, "person not found")

    mentioned = select(MemoryParticipant.memory_id).where(MemoryParticipant.person_id == person_id)
    involves_them = or_(Memory.author_person_id == person_id, Memory.id.in_(mentioned))
    month = local_period(Memory.timestamp, "month")
    timeline = await session.execute(
        select(month, func.count()).where(Memory.user_id == user.id, Memory.timestamp.is_not(None), involves_them)
        .group_by(month).order_by(month))

    conversations = await session.execute(
        select(Conversation.id, Conversation.title, func.count(Memory.id))
        .join(Memory, Memory.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id, Memory.author_person_id == person_id)
        .group_by(Conversation.id, Conversation.title).order_by(func.count(Memory.id).desc()).limit(20))

    summary = _person_out(person, await _message_stats(session, user.id, [person_id]))
    return PersonDetailOut(
        **summary.model_dump(),
        timeline=[PeriodCount(period=period, count=count) for period, count in timeline.all()],
        conversations=[ConversationRef(id=cid, title=title, memory_count=n) for cid, title, n in conversations.all()],
        related_people=[RelatedPerson(id=pid, display_name=name, weight=weight)
                        for pid, name, weight in await related_people(session, user.id, person_id)],
    )
