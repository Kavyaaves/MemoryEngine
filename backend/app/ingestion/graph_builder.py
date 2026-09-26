"""Knowledge-graph edges derived from a conversation (PLAN §12).

    person —PART_OF→ conversation   (weight = how many messages they wrote there)
    person —KNOWS→   person         (both wrote in the same conversation)

Re-running it after an incremental import just updates the weights.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, Relationship

EDGE_KEY = ["user_id", "src_type", "src_id", "rel_type", "dst_type", "dst_id", "source_memory_id"]


def conversation_edge_creator(conversation_id: uuid.UUID) -> str:
    """Tag on every edge built from one conversation, so deleting the chat can delete its edges."""
    return f"parser:conv:{conversation_id}"


async def build_conversation_edges(session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    rows = await session.execute(
        select(Memory.author_person_id, func.count())
        .where(Memory.conversation_id == conversation_id, Memory.author_person_id.is_not(None))
        .group_by(Memory.author_person_id))
    messages_by_person = dict(rows.all())
    if not messages_by_person:
        return

    created_by = conversation_edge_creator(conversation_id)
    edges = []
    for person_id, message_count in messages_by_person.items():
        edges.append({"src_type": "PERSON", "src_id": person_id, "rel_type": "PART_OF",
                      "dst_type": "CONVERSATION", "dst_id": conversation_id, "weight": float(message_count)})
    people = sorted(messages_by_person, key=str)  # fixed order so each pair is stored once
    for i, person_a in enumerate(people):
        for person_b in people[i + 1:]:
            shared = min(messages_by_person[person_a], messages_by_person[person_b])
            edges.append({"src_type": "PERSON", "src_id": person_a, "rel_type": "KNOWS",
                          "dst_type": "PERSON", "dst_id": person_b, "weight": float(shared)})
    for edge in edges:
        edge.update(user_id=user_id, confidence=1.0, created_by=created_by, source_memory_id=None)

    statement = insert(Relationship).values(edges)
    # The edge already exists (earlier import of this chat)? Just refresh its weight.
    statement = statement.on_conflict_do_update(index_elements=EDGE_KEY, set_={"weight": statement.excluded.weight})
    await session.execute(statement)
