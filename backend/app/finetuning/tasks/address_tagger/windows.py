"""Chat windows: the one input format the address_tagger task shows a model.

The teacher (`label`), the training files (`build`), `evaluate` and `apply` all see the same
thing — a window of consecutive messages from one private chat:

    [1] Kavya: Illa kutta
    [2] Nihal: Sorrry kuttaaa
    [3] Kavya: Pothum da

The same input in training and in use is what makes the derived model reliable. The window
also gives context: whether "da" is meant for the other person depends on the messages around it.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, Person, Relationship, User

WINDOW_SIZE = 25  # messages per window (one request to the model)
MAX_MESSAGE_CHARS = 300  # long forwarded texts are cut; address words are almost always near the start


@dataclass
class ChatMessage:
    memory_id: uuid.UUID
    author: str  # a first name, e.g. "Kavya"
    text: str


@dataclass
class PrivateChat:
    """A chat with exactly two writers: the user and one other person."""

    conversation_id: uuid.UUID
    self_id: uuid.UUID
    self_name: str
    other_id: uuid.UUID
    other_name: str


def first_name(display_name: str | None) -> str:
    """'Nihal Manoj' → 'Nihal', 'Rahul ❤️' → 'Rahul'."""
    parts = (display_name or "").split()
    return parts[0] if parts else "Them"


def format_window(messages: list[ChatMessage]) -> str:
    """The text the model reads: one numbered line per message."""
    lines = []
    for number, message in enumerate(messages, start=1):
        text = " ".join(message.text.split())[:MAX_MESSAGE_CHARS]  # one line per message
        lines.append(f"[{number}] {message.author}: {text}")
    return "\n".join(lines)


async def find_user(session: AsyncSession, email: str | None) -> uuid.UUID:
    """The user whose data is used. With one account, `email` isn't needed."""
    query = select(User.id)
    if email:
        query = query.where(User.email == email)
    ids = list((await session.execute(query.limit(2))).scalars())
    if len(ids) == 1:
        return ids[0]
    raise SystemExit("no such user" if not ids else "several users: pass --user-email")


async def private_chats(session: AsyncSession, user_id: uuid.UUID) -> list[PrivateChat]:
    """Every chat where exactly the user and one other person wrote."""
    rows = (await session.execute(
        select(Relationship.dst_id, Relationship.src_id)
        .where(Relationship.user_id == user_id, Relationship.rel_type == "PART_OF",
               Relationship.dst_type == "CONVERSATION"))).all()
    writers: dict[uuid.UUID, list[uuid.UUID]] = {}
    for conversation_id, person_id in rows:
        writers.setdefault(conversation_id, []).append(person_id)

    person_ids = {person_id for _, person_id in rows}
    people = {row.id: row for row in (await session.execute(
        select(Person.id, Person.display_name, Person.is_self).where(Person.id.in_(person_ids)))).all()}

    chats = []
    for conversation_id, ids in writers.items():
        selves = [people[i] for i in ids if i in people and people[i].is_self]
        others = [people[i] for i in ids if i in people and not people[i].is_self]
        if len(ids) == 2 and len(selves) == 1 and len(others) == 1:
            chats.append(PrivateChat(conversation_id, selves[0].id, first_name(selves[0].display_name),
                                     others[0].id, first_name(others[0].display_name)))
    return chats


def _chat_messages_query(chat: PrivateChat, user_id: uuid.UUID, untagged_by: str | None):
    """Messages from both writers of the chat, oldest first."""
    query = select(Memory.id, Memory.text, Memory.author_person_id).where(
        Memory.user_id == user_id, Memory.conversation_id == chat.conversation_id,
        Memory.author_person_id.in_([chat.self_id, chat.other_id]))
    if untagged_by:  # only messages this model hasn't tagged yet (so the tagger can resume)
        tagged_by = func.coalesce(Memory.meta["address_tags"]["model"].astext, "")
        query = query.where(tagged_by != untagged_by)
    return query


async def count_messages(session: AsyncSession, chat: PrivateChat, user_id: uuid.UUID,
                         untagged_by: str | None = None) -> int:
    query = _chat_messages_query(chat, user_id, untagged_by)
    return int((await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one())


async def read_messages(session: AsyncSession, chat: PrivateChat, user_id: uuid.UUID, *, offset: int = 0,
                        limit: int = WINDOW_SIZE, untagged_by: str | None = None) -> list[ChatMessage]:
    query = (_chat_messages_query(chat, user_id, untagged_by)
             .order_by(Memory.timestamp.asc().nulls_last(), Memory.id).offset(offset).limit(limit))
    rows = (await session.execute(query)).all()
    return [ChatMessage(row.id, chat.self_name if row.author_person_id == chat.self_id else chat.other_name, row.text)
            for row in rows]
