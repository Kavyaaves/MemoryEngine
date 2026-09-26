"""The personal Tanglish dictionary stored in `lexicon_entries` (PLAN §7).

- seed_rows(): the built-in word list, inserted once by the first migration.
- learn_from_memories(): after an import, records every Tanglish spelling the user
  actually types and how often ("seriii" → seri ×42). Search already matches these
  spellings through phonetic keys; the table makes them visible and is the dataset for the
  Tanglish-normaliser fine-tuning experiment (PLAN §20A).
"""

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LexiconEntry, Memory
from app.multilingual.lexicon import VARIANT_GROUPS
from app.multilingual.tanglish import lookup_word

BATCH_SIZE = 2000


def seed_rows() -> list[dict]:
    rows = []
    for canonical, (variants, native, gloss) in VARIANT_GROUPS.items():
        spellings = {canonical, *variants} | ({native} if native else set())
        for spelling in spellings:
            rows.append({"surface_form": spelling, "canonical_form": canonical, "language": "tanglish",
                         "gloss": gloss, "source": "seed", "confidence": 1.0, "user_verified": False})
    return rows


async def learn_from_memories(session: AsyncSession, user_id: uuid.UUID, memory_ids: list[uuid.UUID]) -> None:
    counts: Counter[str] = Counter()
    for start in range(0, len(memory_ids), BATCH_SIZE):
        texts = await session.execute(select(Memory.normalized_text).where(
            Memory.id.in_(memory_ids[start:start + BATCH_SIZE]), Memory.language.in_(["tanglish", "mixed"])))
        for text in texts.scalars():
            for token in text.split():
                if token.isascii() and token.isalpha() and len(token) >= 3 and lookup_word(token):
                    counts[token] += 1
    if not counts:
        return

    rows = []
    for spelling, count in counts.items():
        word = lookup_word(spelling)
        rows.append({"user_id": user_id, "surface_form": spelling, "canonical_form": word.canonical,
                     "language": "tanglish", "gloss": word.gloss, "frequency": count, "confidence": 0.8,
                     "source": "corpus"})
    statement = insert(LexiconEntry).values(rows)
    # Seen before? Add to its count instead of inserting a duplicate row.
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "surface_form", "canonical_form"],
        set_={"frequency": LexiconEntry.frequency + statement.excluded.frequency})
    await session.execute(statement)
