"""What every parser produces, plus the hashing that makes re-imports incremental.

    parser(file bytes) → ParseResult(source info, [ParsedRecord, ...])
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedRecord:
    """One message / journal entry / document chunk, straight out of a parser."""

    text: str
    timestamp: datetime | None = None
    author: str | None = None
    record_id: str | None = None  # position in the file, for provenance
    is_system: bool = False  # e.g. "Rahul added Priya" — not stored as a memory
    media_ref: str | None = None  # attached file name, e.g. "IMG-2024-WA0001.jpg"
    meta: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    """Everything parsed from one source (one chat, one journal file)."""

    source_type: str
    source_name: str
    fingerprint: str  # stable identity: the same chat exported twice has the same fingerprint
    records: list[ParsedRecord]
    conversation_title: str | None = None
    participants: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def sha256_hex(*parts: str | bytes) -> str:
    """Hash several values together (with a separator so ("ab","c") ≠ ("a","bc"))."""
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else part.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def content_hashes(fingerprint: str, records: list[ParsedRecord]) -> list[str]:
    """One stable hash per record (PLAN §25 incremental ingestion).

    A re-export of the same chat repeats the whole history, so identical records must hash
    identically — then the pipeline can skip everything it has already stored.
    Two genuinely identical messages ("ok" twice in the same minute) get a counter so
    both are kept.
    """
    seen_count: dict[str, int] = {}
    hashes = []
    for record in records:
        timestamp = record.timestamp.isoformat() if record.timestamp else ""
        base = sha256_hex(fingerprint, timestamp, record.author or "", record.text)
        n = seen_count.get(base, 0)
        seen_count[base] = n + 1
        hashes.append(base if n == 0 else sha256_hex(base, str(n)))
    return hashes


def decode_text(data: bytes) -> str:
    """Decode an uploaded text file. WhatsApp uses UTF-8; some Windows tools write UTF-16."""
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails; better garbled than rejected
