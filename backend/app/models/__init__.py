"""Database tables (the canonical memory model, PLAN §5).

PostgreSQL is the source of truth. Each file groups related tables:

    user.py     User
    source.py   Source, IngestionJob, Conversation      — where memories come from
    memory.py   Memory, MemoryParticipant, MediaAsset   — the memories themselves
    person.py   Person, PersonAlias                     — people and their names
    graph.py    Relationship, Event, Place              — the knowledge graph (an Event is a Memory Book)
    universe.py MemoryPage, MemoryPageItem,
                UniverseChange                          — the Memory Universe (derived, rebuildable)
    lexicon.py  LexiconEntry                            — personal Tanglish dictionary
    usage.py    AIUsage, AuditLog                       — bookkeeping
"""

from app.models.graph import Event, Place, Relationship
from app.models.lexicon import LexiconEntry
from app.models.memory import EMBEDDING_DIM, MediaAsset, Memory, MemoryParticipant
from app.models.person import AliasStatus, Person, PersonAlias
from app.models.source import Conversation, IngestionJob, JobStatus, Source
from app.models.universe import MemoryPage, MemoryPageItem, UniverseChange
from app.models.usage import AIUsage, AuditLog
from app.models.user import User

__all__ = [
    "EMBEDDING_DIM", "AIUsage", "AliasStatus", "AuditLog", "Conversation", "Event", "IngestionJob", "JobStatus",
    "LexiconEntry", "MediaAsset", "Memory", "MemoryPage", "MemoryPageItem", "MemoryParticipant", "Person",
    "PersonAlias", "Place", "Relationship", "Source", "UniverseChange", "User",
]
