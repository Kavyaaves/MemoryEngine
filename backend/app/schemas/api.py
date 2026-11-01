"""HTTP API models — mirror docs/api-contract.md."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    source_id: uuid.UUID | None
    filename: str
    source_type: str
    status: str
    progress: float
    stats: dict
    error: str | None
    created_at: datetime
    updated_at: datetime


class JobsOut(BaseModel):
    jobs: list[JobOut]


class SourceOut(BaseModel):
    id: uuid.UUID
    source_type: str
    name: str
    memory_count: int
    created_at: datetime
    last_processed_at: datetime | None


class MediaRef(BaseModel):
    id: uuid.UUID
    kind: str
    url: str
    mime_type: str | None


class SentimentOut(BaseModel):
    label: Literal["positive", "negative", "neutral"]
    score: float  # the model's confidence, 0.5..1


class Evidence(BaseModel):
    memory_id: uuid.UUID
    source_type: str
    source_name: str
    conversation_id: uuid.UUID | None
    conversation_title: str | None
    timestamp: datetime | None
    author: str | None
    text: str
    snippet: str
    language: str
    script: str
    score: float
    retrieval_paths: list[str]
    media: list[MediaRef] = Field(default_factory=list)
    sentiment: SentimentOut | None = None  # None: not analysed yet, or nothing to analyse
    # Where the memory lives in the Memory Universe (None until the universe update has placed it).
    book_id: uuid.UUID | None = None
    book_title: str | None = None
    page_id: uuid.UUID | None = None


class SearchOut(BaseModel):
    results: list[Evidence]
    timings_ms: dict[str, int]


class PhotoOut(BaseModel):
    """One uploaded photo: its metadata and the user's caption (the picture itself is never analysed)."""

    memory_id: uuid.UUID
    filename: str
    url: str
    mime_type: str | None
    timestamp: datetime | None  # the date it has in the timeline
    date_source: str  # exif_taken | filename | exif_changed | file_modified | uploaded
    taken_at: datetime | None
    changed_at: datetime | None
    file_modified_at: datetime | None
    uploaded_at: datetime
    caption: str
    caption_status: Literal["none", "pending", "ingested"]


class PhotosOut(BaseModel):
    photos: list[PhotoOut]
    pending_captions: int  # captions saved but not ingested yet (for the whole library, not only this page)


class CaptionIn(BaseModel):
    caption: str = Field(max_length=2000)


class CaptionIngestOut(BaseModel):
    ingested: int
    embedded: int
    sentiment: int  # captions whose sentiment was analysed


class MoodBucket(BaseModel):
    period: str
    positive: int
    negative: int
    neutral: int
    mood: float  # (positive − negative) / all analysed, from −1 (all negative) to +1 (all positive)


class MoodTimelineOut(BaseModel):
    buckets: list[MoodBucket]


class SentimentStatusOut(BaseModel):
    enabled: bool
    installed: bool  # are transformers + torch installed?
    model: str
    done: int  # this user's memories that have been analysed
    remaining: int
    running: bool  # is an "analyse now" run going on for this user?


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation: list[ChatTurn] = Field(default_factory=list, max_length=20)


class AnalysisOut(BaseModel):
    intent: str
    people: list[str]
    time_start: str | None
    time_end: str | None
    temporal_order: str | None
    modality: list[str]
    rewritten_queries: list[str]


class TraceStep(BaseModel):
    name: str
    latency_ms: int
    detail: str | None = None


class FinetuneOut(BaseModel):
    """The two fine-tuning labels (app/finetuning/)."""

    base_model: str  # the standard model the training lineage started from, e.g. "gpt-4.1-nano-2025-04-14"
    derived_model: str  # the model we trained from it, e.g. "ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123"


class TraceOut(BaseModel):
    steps: list[TraceStep]
    provider: str | None
    model: str | None
    degraded: bool
    # Set when the fine-tuning phase's derived model (app/finetuning/) helped with this answer.
    finetune: FinetuneOut | None = None


class AskOut(BaseModel):
    answer: str
    evidence: list[Evidence]
    confidence: Literal["high", "medium", "low", "none"]
    analysis: AnalysisOut
    trace: TraceOut


class TimelineBucket(BaseModel):
    period: str
    count: int
    sources: dict[str, int]
    top_people: list[str]


class TimelineOut(BaseModel):
    buckets: list[TimelineBucket]


class DayOut(BaseModel):
    date: str
    memories: list[Evidence]


class PersonOut(BaseModel):
    id: uuid.UUID
    display_name: str
    aliases: list[str]
    memory_count: int
    first_seen: datetime | None
    last_seen: datetime | None


class PeriodCount(BaseModel):
    period: str
    count: int


class ConversationRef(BaseModel):
    id: uuid.UUID
    title: str
    memory_count: int


class RelatedPerson(BaseModel):
    id: uuid.UUID
    display_name: str
    weight: float


class PersonDetailOut(PersonOut):
    timeline: list[PeriodCount]
    conversations: list[ConversationRef]
    related_people: list[RelatedPerson]


class AliasSuggestionOut(BaseModel):
    alias_id: uuid.UUID
    alias: str
    person_id: uuid.UUID
    person_name: str
    similarity: float


class AliasFeedbackIn(BaseModel):
    alias_id: uuid.UUID
    person_id: uuid.UUID
    answer: Literal["yes", "no", "unsure"]


# ---- Memory Universe (app/universe/, api/universe.py) ----

class PersonRef(BaseModel):
    id: uuid.UUID
    name: str
    count: int  # memories they wrote or were mentioned in


class BookOut(BaseModel):
    """A Memory Book as the 3D scene needs it."""

    id: uuid.UUID
    title: str
    title_source: Literal["auto", "ai", "user"]
    event_type: str
    start_at: datetime
    end_at: datetime
    memory_count: int
    page_count: int
    photo_count: int
    people: list[PersonRef]  # the most involved first (at most 5)
    position: tuple[float, float, float]  # stored once when the book was created; never changes
    updated_at: datetime


class UniverseLayoutOut(BaseModel):
    """The constants the client needs to draw year gates exactly where the server puts books."""

    origin: str  # "2000-01-01"
    units_per_day: float
    river_radius: float


class UniversePeriod(BaseModel):
    period: str  # "2024" or "2024-06"
    memory_count: int
    book_count: int = 0


class UniverseOut(BaseModel):
    layout: UniverseLayoutOut
    years: list[UniversePeriod]
    months: list[UniversePeriod]
    books: list[BookOut]
    cursor: int  # the latest change id; poll /universe/changes?after=<cursor>
    unplaced_memories: int  # dated memories not in the universe yet (a build is needed)
    undated_memories: int  # memories without a date: searchable, but not placed in time


class PageOut(BaseModel):
    id: uuid.UUID
    day: str  # YYYY-MM-DD
    start_at: datetime
    end_at: datetime
    memory_count: int
    photo_count: int
    people: list[PersonRef]
    preview: str
    thread_name: str  # the conversation / source name, or "Photos & media"


class RelatedBookOut(BaseModel):
    book: BookOut
    reason: Literal["same_person", "similar_memories"]
    label: str  # e.g. "Rahul is in both" · "Similar conversations (0.86)"


class BookDetailOut(BaseModel):
    book: BookOut
    summary: str | None
    summary_memory_ids: list[uuid.UUID]  # the memories an AI summary was written from (empty for auto titles)
    places: list[str]
    pages: list[PageOut]
    related: list[RelatedBookOut]


class PageDetailOut(BaseModel):
    page: PageOut
    book_id: uuid.UUID | None
    book_title: str | None
    memories: list[Evidence]
    total: int


class MemoryLocationOut(BaseModel):
    """The path the camera travels: Universe → year → month → book → page → memory."""

    memory_id: uuid.UUID
    year: str
    month: str  # YYYY-MM
    day: str  # YYYY-MM-DD
    book_id: uuid.UUID
    book_title: str
    page_id: uuid.UUID
    position: tuple[float, float, float]


class ConnectionOut(BaseModel):
    kind: str  # same_event | same_person | previous_mention | later_reference | similar | related_photo
    label: str
    similarity: float | None
    memory: Evidence
    location: MemoryLocationOut | None


class MemoryDetailOut(BaseModel):
    memory: Evidence  # the original, unmodified text with its source
    location: MemoryLocationOut | None
    context: list[Evidence]  # the messages just before and after it in the same conversation
    connections: list[ConnectionOut]


class UniverseChangeOut(ORM):
    id: int
    job_id: uuid.UUID | None
    kind: str
    entity_type: str
    entity_id: uuid.UUID | None
    detail: dict
    created_at: datetime


class UniverseChangesOut(BaseModel):
    cursor: int
    changes: list[UniverseChangeOut]


class UniverseBuildOut(BaseModel):
    status: Literal["queued", "inline"]


class BookRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
