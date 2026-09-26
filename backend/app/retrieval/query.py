"""Building blocks shared by every search path: filters, candidates, and the keyword query."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, or_, select

from app.models import Memory, MemoryParticipant

# Full-text search uses PostgreSQL's 'simple' configuration (there's no Tamil/Tanglish
# dictionary), which keeps every word — so common English words are removed here instead.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "to", "of", "in", "on", "at", "for", "with",
    "and", "or", "but", "i", "me", "my", "we", "our", "you", "your", "it", "this", "that", "what", "when",
    "where", "who", "why", "how", "did", "do", "does", "about", "from", "by", "as", "so", "show", "find",
    "tell", "any", "all", "have", "has", "had", "there", "their", "them", "they", "he", "she", "his", "her",
    "memories", "memory", "messages", "message", "time", "first", "last", "ever", "say", "said",
}
MAX_QUERY_TERMS = 24
SAFE_TERM = re.compile(r"^[\w\u0B80-\u0BFF\u0D00-\u0D7F]+$")  # letters/digits only — nothing to escape


@dataclass
class SearchFilters:
    """Restrictions applied to every search path. Dates must be timezone-aware."""

    user_id: uuid.UUID
    start: datetime | None = None
    end: datetime | None = None  # exclusive
    person_ids: list[uuid.UUID] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    conversation_id: uuid.UUID | None = None

    def apply(self, query, *, include_people: bool = True):
        """Add the WHERE clauses to a SELECT over `memories`."""
        query = query.where(Memory.user_id == self.user_id)  # users only ever see their own data
        if self.start:
            query = query.where(Memory.timestamp >= self.start)
        if self.end:
            query = query.where(Memory.timestamp < self.end)
        if self.source_types:
            query = query.where(Memory.source_type.in_(self.source_types))
        if self.conversation_id:
            query = query.where(Memory.conversation_id == self.conversation_id)
        if include_people and self.person_ids:
            mentioned = select(MemoryParticipant.memory_id).where(MemoryParticipant.person_id.in_(self.person_ids))
            query = query.where(or_(Memory.author_person_id.in_(self.person_ids), Memory.id.in_(mentioned)))
        return query


@dataclass
class Candidate:
    """One search path's opinion: this memory, with this score."""

    memory_id: uuid.UUID
    score: float
    path: str  # fts | trgm | vector | graph | temporal


def content_terms(terms: list[str]) -> list[str]:
    """Drop stopwords, punctuation-bearing tokens and single Latin letters."""
    return [t for t in terms
            if t not in STOPWORDS and SAFE_TERM.match(t) and (len(t) > 1 or not t.isascii())]


def keyword_query(terms: list[str]):
    """A PostgreSQL tsquery matching ANY of the terms ('kerala' | 'trip'), or None.

    OR (not AND) because a Tanglish query expands to many spellings; the ranking function
    then rewards memories that match more of them.
    """
    safe_terms = content_terms(terms)[:MAX_QUERY_TERMS]
    if not safe_terms:
        return None
    return func.to_tsquery("simple", " | ".join(f"'{t}'" for t in safe_terms))
