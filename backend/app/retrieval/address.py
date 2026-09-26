"""How the user addresses someone, or how someone addresses the user.

    "How do I call Nihal?"      → the pet names / "hey" words in the messages YOU wrote to Nihal
    "What does Nihal call me?"  → the same, in the messages NIHAL wrote to you

This is counting, not searching: the answer ("da", "kutta", "chellakutty"…) is spread over
thousands of messages that don't contain any word of the question, so keyword or semantic
search can never find it. Instead we read every message in the chat with that person and
count the address words in them.

Which words are address words — two ways, and the report says which one was used:
    1. DERIVED MODEL  the model trained in the fine-tuning phase (app/finetuning/, task
                      "address_tagger") has already tagged the message: memories.meta["address_tags"]
    2. BASELINE       the hand-written word list (multilingual/lexicon.py ADDRESS_TERMS), plus the
                      person's own name — for every message the current derived model hasn't tagged
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finetuning import base_model, derived_model
from app.models import Memory, Person, Relationship
from app.multilingual.lexicon import ADDRESS_TERMS
from app.multilingual.normalization import normalize, words

MAX_TERMS_REPORTED = 8
EXAMPLES_PER_TERM = 2
EXAMPLE_TERMS = 5  # example messages are shown for the top 5 words only

# (canonical, compiled regex, gloss) — compiled once, when the module is imported.
_PATTERNS = [(canonical, re.compile(pattern), gloss) for canonical, pattern, gloss in ADDRESS_TERMS]


@dataclass
class AddressTerm:
    term: str  # canonical form, e.g. "kutta"
    gloss: str  # e.g. "little one"
    messages: int = 0  # how many messages use it (a message counts once, however often it repeats the word)
    spellings: Counter = field(default_factory=Counter)  # "kutta" → 157, "kuttaa" → 77
    example_ids: list[uuid.UUID] = field(default_factory=list)


def classify_word(word: str, name_words: set[str]) -> tuple[str, str] | None:
    """('kutta', 'little one') if `word` is an address word, ('Nihal', 'their name') for their name, else None."""
    if word in name_words:
        return word.capitalize(), "their name"
    for canonical, pattern, gloss in _PATTERNS:
        if pattern.fullmatch(word):
            return canonical, gloss
    return None


def tagged_words(tags: dict | None, model: str | None) -> list[str] | None:
    """The address words the derived model `model` stored for a message — or None if it hasn't
    tagged it (then the word list is used). Tags by an older derived model don't count."""
    if model and tags and tags.get("model") == model:
        return tags.get("words") or []
    return None


def tally_address_terms(messages: list[tuple[uuid.UUID, str, dict | None]], name_words: set[str],
                        model: str | None = None) -> list[AddressTerm]:
    """Count address words in (memory id, text, stored address tags) triples. Most used first.

    `model` is the current derived model (None = word list only).
    `messages` should be newest first: the first few messages seen for a word become its examples.
    """
    found: dict[str, AddressTerm] = {}
    for memory_id, text, tags in messages:
        from_model = tagged_words(tags, model)
        if from_model is not None:  # 1. the derived model read this message
            address_words = [normalize(w) for w in from_model]
        else:  # 2. baseline: the word list
            address_words = [w for w in words(normalize(text)) if classify_word(w, name_words)]

        terms_in_this_message = set()
        for word in address_words:
            # Group spellings under the word list's name ("kuttaa" → "kutta"). A word the list
            # doesn't know is a new nickname only the derived model found: it keeps its own name.
            canonical, gloss = classify_word(word, name_words) or (word, "found by the derived model")
            entry = found.setdefault(canonical, AddressTerm(canonical, gloss))
            entry.spellings[word] += 1
            terms_in_this_message.add(canonical)
        for canonical in terms_in_this_message:
            entry = found[canonical]
            entry.messages += 1
            if len(entry.example_ids) < EXAMPLES_PER_TERM:
                entry.example_ids.append(memory_id)
    return sorted(found.values(), key=lambda t: t.messages, reverse=True)


@dataclass
class AddressReport:
    person_name: str
    speaker: str  # "self" = how the user addresses them; "them" = how they address the user
    one_to_one: bool  # True when counted in a private chat only (not group chats)
    message_count: int  # how many messages were read
    terms: list[AddressTerm]
    derived_model: str | None = None  # the derived model whose tags were used ("ft:…"), if any
    tagged_messages: int = 0  # how many of the messages it had tagged (the rest used the word list)

    @property
    def used_derived_model(self) -> bool:
        return self.tagged_messages > 0

    def method(self) -> str:
        """How the address words were found — the derived model, the word list, or both."""
        if not self.used_derived_model:
            return "Method: the hand-written word list (no derived model has tagged these messages yet)."
        rest = self.message_count - self.tagged_messages
        return (f"Method: the derived model {self.derived_model} (fine-tuned from the base model {base_model()}) "
                f"found the address words in {self.tagged_messages} of the {self.message_count} messages"
                + (f"; the hand-written word list was used for the other {rest}." if rest else "."))

    def example_ids(self) -> list[uuid.UUID]:
        """Example messages for the top words, in the order of the words."""
        ids = []
        for term in self.terms[:EXAMPLE_TERMS]:
            ids += [i for i in term.example_ids if i not in ids]
        return ids

    def as_fact(self) -> str:
        """One line for the answer prompt, e.g. FACT (computed by SQL): … "da" in 734 messages …"""
        where = f"your private chat with {self.person_name}" if self.one_to_one \
            else f"the chats you share with {self.person_name}"
        who = f"the {self.message_count} messages you wrote to them" if self.speaker == "self" \
            else f"the {self.message_count} messages {self.person_name} wrote to you"
        shown = self.terms[:MAX_TERMS_REPORTED]
        name_terms = [t for t in self.terms[MAX_TERMS_REPORTED:] if t.gloss == "their name"]
        parts = []
        for t in shown + name_terms:  # always mention the person's name, even if it is rarely used
            spellings = ", ".join(f"{s} ×{n}" for s, n in t.spellings.most_common(3))
            parts.append(f'"{t.term}" ({t.gloss}) in {t.messages} messages [{spellings}]')
        return (f"FACT (computed by SQL): In {where}, {who} were read and the words used to address "
                f"{'them' if self.speaker == 'self' else 'you'} were counted (most used first): "
                + "; ".join(parts) + ". " + self.method()
                + " The numbered evidence holds example messages for the top words: "
                "cite those by their own number, e.g. [2]. This FACT line has no number, so don't cite it.")


async def _conversations_with(session: AsyncSession, user_id: uuid.UUID,
                              person_id: uuid.UUID) -> tuple[list[uuid.UUID], bool]:
    """The chats this person writes in. Private (2-person) chats only, if there are any —
    in a group chat, a "da" could be meant for anyone."""
    shared = select(Relationship.dst_id).where(
        Relationship.user_id == user_id, Relationship.rel_type == "PART_OF", Relationship.src_id == person_id)
    rows = (await session.execute(
        select(Relationship.dst_id, func.count(Relationship.src_id))
        .where(Relationship.user_id == user_id, Relationship.rel_type == "PART_OF", Relationship.dst_id.in_(shared))
        .group_by(Relationship.dst_id))).all()
    private = [conversation_id for conversation_id, writers in rows if writers <= 2]
    if private:
        return private, True
    return [conversation_id for conversation_id, _ in rows], False


async def count_address_terms(session: AsyncSession, user_id: uuid.UUID, person_id: uuid.UUID,
                              person_name: str, speaker: str = "self") -> AddressReport:
    conversation_ids, one_to_one = await _conversations_with(session, user_id, person_id)

    query = (select(Memory.id, Memory.normalized_text, Memory.meta["address_tags"].label("tags"))
             .join(Person, Person.id == Memory.author_person_id)
             .where(Memory.user_id == user_id, Memory.conversation_id.in_(conversation_ids))
             .order_by(Memory.timestamp.desc().nulls_last()))
    if speaker == "self":
        query = query.where(Person.is_self.is_(True))  # what the user wrote
    else:
        query = query.where(Memory.author_person_id == person_id)  # what they wrote
    messages = (await session.execute(query)).all() if conversation_ids else []

    name_words = {w for w in words(normalize(person_name)) if len(w) > 2}  # "Nihal Manoj" → {"nihal", "manoj"}
    model = derived_model()  # None until the fine-tuning phase has produced one
    rows = [(m.id, m.normalized_text, m.tags) for m in messages]
    terms = tally_address_terms(rows, name_words, model)
    tagged = sum(1 for _, _, tags in rows if tagged_words(tags, model) is not None)
    return AddressReport(person_name=person_name, speaker=speaker, one_to_one=one_to_one,
                         message_count=len(messages), terms=terms, derived_model=model, tagged_messages=tagged)
