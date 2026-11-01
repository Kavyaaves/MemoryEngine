"""Deciding which Memory Book each new page belongs to. Pure logic: no database, no AI.

    plan_books(pages, nearby_books) → BookPlan
        for each page, oldest first:
            already in a book?  → that book is "touched" (it gained memories); nothing moves
            otherwise           → attach it to the best matching nearby book,
                                  or start a new book if none matches well enough

How well a page matches a book (0..1):

    0.55 × meaning   cosine similarity of the page's average embedding and the book's
    0.25 × people    how many of the page's people are already in the book (Jaccard overlap)
    0.10 × thread    1 if the book already has pages from the same conversation
    0.10 × nearness  1 on the same day, falling to 0 at ATTACH_WINDOW_DAYS apart

A page may only join a book that ends at most ATTACH_WINDOW_DAYS before it (or starts at
most that long after it), and only if the book would still cover MAX_BOOK_SPAN_DAYS or fewer:
events have a beginning and an end, so a chat you have every day becomes a series of
chapters rather than one endless book.

Pages without embeddings yet (the provider was down) are matched on people, thread and time
only. Photo/audio/video pages have no meaningful text, so they join the busiest book that
covers their day — "the photos from the trip" — or start a photo book of their own.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np

from app.universe.layout import Position, place_book

ATTACH_WINDOW_DAYS = 2
MAX_BOOK_SPAN_DAYS = 21
MIN_MATCH_SCORE = 0.55
MEDIA_THREAD = "media"  # thread_key of photo/audio/video pages (see pages.py)

WEIGHT_MEANING = 0.55
WEIGHT_PEOPLE = 0.25
WEIGHT_THREAD = 0.10
WEIGHT_NEARNESS = 0.10


@dataclass
class PageInfo:
    """A page as the planner sees it (loaded by pages.py after its counts were refreshed)."""

    id: uuid.UUID
    thread_key: str
    day: date
    start_at: datetime
    end_at: datetime
    memory_count: int
    photo_count: int = 0
    people: dict[str, int] = field(default_factory=dict)  # person id → messages (the user themself excluded)
    centroid: np.ndarray | None = None
    centroid_count: int = 0
    event_id: uuid.UUID | None = None  # its book, if it already has one

    @property
    def is_media(self) -> bool:
        return self.thread_key == MEDIA_THREAD


@dataclass
class BookInfo:
    """A book as the planner sees it: an existing one loaded from the database, or one it creates."""

    id: uuid.UUID
    start_day: date
    end_day: date
    lane_key: str
    position: Position
    memory_count: int = 0
    people: Counter = field(default_factory=Counter)
    thread_keys: set[str] = field(default_factory=set)
    centroid: np.ndarray | None = None
    centroid_count: int = 0
    is_new: bool = False  # created by this plan

    @property
    def span_days(self) -> int:
        return (self.end_day - self.start_day).days


@dataclass
class BookPlan:
    new_books: list[BookInfo] = field(default_factory=list)
    assignments: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)  # page id → book id (new placements)
    scores: dict[uuid.UUID, float] = field(default_factory=dict)  # page id → match score, for attached pages
    touched_book_ids: set[uuid.UUID] = field(default_factory=set)  # books whose contents changed (incl. new)

    @property
    def updated_book_ids(self) -> set[uuid.UUID]:
        """Existing books that gained memories."""
        return self.touched_book_ids - {book.id for book in self.new_books}


# ---- scoring -----------------------------------------------------------------------------

def cosine(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    if a is None or b is None:
        return None
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b)) / denominator if denominator else None


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def gap_days(page: PageInfo, book: BookInfo) -> int:
    """Days between the page and the book (0 if the page's day is inside the book)."""
    if page.day > book.end_day:
        return (page.day - book.end_day).days
    if page.day < book.start_day:
        return (book.start_day - page.day).days
    return 0


def can_join(page: PageInfo, book: BookInfo) -> bool:
    if gap_days(page, book) > ATTACH_WINDOW_DAYS:
        return False
    new_span = (max(book.end_day, page.day) - min(book.start_day, page.day)).days
    return new_span <= MAX_BOOK_SPAN_DAYS


def match_score(page: PageInfo, book: BookInfo) -> float | None:
    """How well `page` fits `book` (0..1), or None when it may not join it at all."""
    if not can_join(page, book):
        return None
    people = jaccard(set(page.people), set(book.people))
    thread = 1.0 if page.thread_key in book.thread_keys else 0.0
    nearness = 1.0 - gap_days(page, book) / (ATTACH_WINDOW_DAYS + 1)
    meaning = cosine(page.centroid, book.centroid)
    if meaning is None:
        # No embeddings to compare: judge on the other signals alone, scaled back up to 0..1.
        other_weights = WEIGHT_PEOPLE + WEIGHT_THREAD + WEIGHT_NEARNESS
        return (WEIGHT_PEOPLE * people + WEIGHT_THREAD * thread + WEIGHT_NEARNESS * nearness) / other_weights
    return WEIGHT_MEANING * max(0.0, meaning) + WEIGHT_PEOPLE * people + WEIGHT_THREAD * thread \
        + WEIGHT_NEARNESS * nearness


def lane_for(page: PageInfo) -> str:
    """The lane of a book started by this page: its main person, else its conversation."""
    if page.people:
        # most messages first; ties broken by id so the result never depends on dict order
        return min(page.people.items(), key=lambda item: (-item[1], item[0]))[0]
    return page.thread_key


# ---- planning ----------------------------------------------------------------------------

def _add_page(book: BookInfo, page: PageInfo) -> None:
    """Update the planner's picture of a book after a page joins it (the database recounts
    everything precisely afterwards; this only has to be good enough for the next page)."""
    book.start_day = min(book.start_day, page.day)
    book.end_day = max(book.end_day, page.day)
    book.memory_count += page.memory_count
    book.people.update(page.people)
    book.thread_keys.add(page.thread_key)
    if page.centroid is not None and page.centroid_count:
        if book.centroid is None or not book.centroid_count:
            book.centroid, book.centroid_count = page.centroid, page.centroid_count
        else:  # weighted running mean: (old × n + new × m) / (n + m)
            total = book.centroid_count + page.centroid_count
            book.centroid = (book.centroid * book.centroid_count + page.centroid * page.centroid_count) / total
            book.centroid_count = total


def _best_book(page: PageInfo, books: list[BookInfo]) -> tuple[BookInfo | None, float]:
    if page.is_media:
        # Photos join the busiest book that covers their day (score 1: time is the only signal we have).
        covering = [b for b in books if can_join(page, b) and gap_days(page, b) <= 1]
        if not covering:
            return None, 0.0
        return max(covering, key=lambda b: (b.memory_count, str(b.id))), 1.0
    scored = [(score, book) for book in books if (score := match_score(page, book)) is not None]
    if not scored:
        return None, 0.0
    # highest score wins; ties go to the smaller id so the result is the same every run
    score, book = max(scored, key=lambda pair: (pair[0], -int(pair[1].id)))
    return (book, score) if score >= MIN_MATCH_SCORE else (None, score)


def plan_books(pages: list[PageInfo], nearby_books: list[BookInfo],
               new_id: Callable[[], uuid.UUID] = uuid.uuid4) -> BookPlan:
    """Decide books for `pages` (the pages an import added to or created).

    `nearby_books`: existing books around the pages' dates — their positions keep new books from
    overlapping them, and they are the candidates new pages can join. They are never moved.
    """
    plan = BookPlan()
    books = list(nearby_books)
    by_id = {book.id: book for book in books}

    for page in sorted(pages, key=lambda p: (p.start_at, p.thread_key, str(p.id))):
        if page.event_id is not None:  # already in a book: it just grew
            plan.touched_book_ids.add(page.event_id)
            continue
        book, score = _best_book(page, books)
        if book is None:
            lane = MEDIA_THREAD if page.is_media else lane_for(page)
            position = place_book(page.start_at, lane, [b.position for b in books])
            book = BookInfo(id=new_id(), start_day=page.day, end_day=page.day, lane_key=lane,
                            position=position, is_new=True)
            books.append(book)
            by_id[book.id] = book
            plan.new_books.append(book)
        else:
            plan.scores[page.id] = round(score, 4)
        _add_page(book, page)
        plan.assignments[page.id] = book.id
        plan.touched_book_ids.add(book.id)
    return plan
