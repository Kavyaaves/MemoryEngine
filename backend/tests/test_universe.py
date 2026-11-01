"""The Memory Universe (app/universe/): incremental placement, event matching, graph, positions.

No database is needed: the decisions live in pure functions (matching.plan_books, layout.place_book,
graph.new_person_links, titles.*, changes.describe), the pipeline test replaces every database
step with a recorder, and the SQL is compiled against the PostgreSQL dialect like test_sql_compile.
"""

import itertools
import math
import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
from sqlalchemy.dialects import postgresql

from app.ingestion.records import ParsedRecord, content_hashes
from app.universe import changes, graph, layout, matching, titles
from app.universe.books import BookChange
from app.universe.matching import MEDIA_THREAD, BookInfo, PageInfo, plan_books

POSTGRES = postgresql.dialect()
RNG = np.random.default_rng(7)
TRIP_TOPIC = RNG.normal(size=768)  # "Andhra trip" conversations point roughly this way
WORK_TOPIC = RNG.normal(size=768)
BIRTHDAY_TOPIC = RNG.normal(size=768)
NEW_TOPIC = RNG.normal(size=768)
RAHUL, PRIYA, MANAGER, AMMA = (str(uuid.UUID(int=i)) for i in (101, 102, 103, 104))
TRIP_CHAT, WORK_CHAT, FAMILY_CHAT, NEW_CHAT = "chat-trip", "chat-work", "chat-family", "chat-new"


def near(topic: np.ndarray, noise: float = 0.3) -> np.ndarray:
    """A page centroid close to `topic` (cosine ≈ 0.95)."""
    return topic + RNG.normal(size=768) * noise


def when(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def page(day: date, thread: str, people: dict[str, int], topic: np.ndarray | None, count: int = 20,
         event_id: uuid.UUID | None = None) -> PageInfo:
    return PageInfo(id=uuid.uuid4(), thread_key=thread, day=day, start_at=when(day, 9), end_at=when(day, 21),
                    memory_count=count, people=people, centroid=None if topic is None else near(topic),
                    centroid_count=0 if topic is None else count, event_id=event_id)


def book(start: date, end: date, thread: str, people: dict[str, int], topic: np.ndarray, count: int = 100,
         lane: str | None = None) -> BookInfo:
    lane = lane or thread
    return BookInfo(id=uuid.uuid4(), start_day=start, end_day=end, lane_key=lane,
                    position=layout.place_book(when(start), lane, []), memory_count=count,
                    people=Counter(people), thread_keys={thread}, centroid=near(topic, 0.1), centroid_count=count)


def sequential_ids():
    counter = itertools.count(1)
    return lambda: uuid.UUID(int=10_000 + next(counter))


# ---- existing event matching / new event creation ------------------------------------------------

def test_the_example_from_the_brief_80_messages_join_the_trip_and_120_start_a_new_book():
    """Existing 2025: Andhra Trip, Birthday, Work. 200 new messages: 80 from the trip, 120 from a new event."""
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60, PRIYA: 40}, TRIP_TOPIC)
    birthday = book(date(2025, 5, 2), date(2025, 5, 2), FAMILY_CHAT, {AMMA: 30}, BIRTHDAY_TOPIC)
    work = book(date(2025, 6, 1), date(2025, 6, 18), WORK_CHAT, {MANAGER: 90}, WORK_TOPIC)

    trip_pages = [page(date(2025, 3, 15), TRIP_CHAT, {RAHUL: 25, PRIYA: 15}, TRIP_TOPIC, count=40),
                  page(date(2025, 3, 16), TRIP_CHAT, {RAHUL: 20, PRIYA: 20}, TRIP_TOPIC, count=40)]
    new_pages = [page(date(2025, 8, 1) + timedelta(days=i), NEW_CHAT, {str(uuid.UUID(int=200)): 30}, NEW_TOPIC,
                      count=40) for i in range(3)]

    plan = plan_books(trip_pages + new_pages, [trip, birthday, work])

    assert all(plan.assignments[p.id] == trip.id for p in trip_pages)  # 80 messages → new pages of Andhra Trip
    assert len(plan.new_books) == 1  # 120 messages → one newly discovered event
    assert all(plan.assignments[p.id] == plan.new_books[0].id for p in new_pages)
    assert plan.updated_book_ids == {trip.id}  # Birthday and Work are untouched
    assert all(plan.scores[p.id] >= matching.MIN_MATCH_SCORE for p in trip_pages)


def test_first_import_creates_books_from_nothing():
    pages = [page(date(2024, 6, 14) + timedelta(days=i), TRIP_CHAT, {RAHUL: 10}, TRIP_TOPIC) for i in range(4)]
    plan = plan_books(pages, [])
    assert len(plan.new_books) == 1
    assert set(plan.assignments.values()) == {plan.new_books[0].id}
    assert plan.new_books[0].lane_key == RAHUL  # the main person decides the lane


def test_a_page_far_from_every_book_starts_a_new_book():
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60}, TRIP_TOPIC)
    later = page(date(2025, 3, 14) + timedelta(days=matching.ATTACH_WINDOW_DAYS + 1), TRIP_CHAT, {RAHUL: 5}, TRIP_TOPIC)
    plan = plan_books([later], [trip])
    assert plan.assignments[later.id] != trip.id and len(plan.new_books) == 1


def test_a_different_topic_with_different_people_on_the_same_day_is_a_separate_book():
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60, PRIYA: 30}, TRIP_TOPIC)
    work_day = page(date(2025, 3, 12), WORK_CHAT, {MANAGER: 12}, WORK_TOPIC)
    plan = plan_books([work_day], [trip])
    assert plan.assignments[work_day.id] != trip.id


def test_a_daily_chat_becomes_chapters_instead_of_one_endless_book():
    pages = [page(date(2024, 1, 1) + timedelta(days=i), TRIP_CHAT, {PRIYA: 10}, TRIP_TOPIC) for i in range(60)]
    plan = plan_books(pages, [])
    assert len(plan.new_books) >= 3  # 60 days / MAX_BOOK_SPAN_DAYS (21)
    assert all(b.span_days <= matching.MAX_BOOK_SPAN_DAYS for b in plan.new_books)


def test_pages_without_embeddings_are_matched_on_people_thread_and_time():
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60}, TRIP_TOPIC)
    trip.centroid = None
    same_chat = page(date(2025, 3, 15), TRIP_CHAT, {RAHUL: 4}, topic=None)
    other_chat = page(date(2025, 3, 15), WORK_CHAT, {MANAGER: 4}, topic=None)
    plan = plan_books([same_chat, other_chat], [trip])
    assert plan.assignments[same_chat.id] == trip.id
    assert plan.assignments[other_chat.id] != trip.id


def test_photos_join_the_busiest_book_of_their_day_or_start_a_photo_book():
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60}, TRIP_TOPIC, count=300)
    quiet = book(date(2025, 3, 12), date(2025, 3, 12), WORK_CHAT, {MANAGER: 3}, WORK_TOPIC, count=3)
    trip_photos = page(date(2025, 3, 12), MEDIA_THREAD, {}, topic=None, count=12)
    lone_photos = page(date(2025, 9, 1), MEDIA_THREAD, {}, topic=None, count=5)
    plan = plan_books([trip_photos, lone_photos], [trip, quiet])
    assert plan.assignments[trip_photos.id] == trip.id
    photo_book = next(b for b in plan.new_books if b.id == plan.assignments[lone_photos.id])
    assert photo_book.lane_key == MEDIA_THREAD


# ---- duplicate upload / new memory ingestion ------------------------------------------------------

def test_duplicate_upload_hashes_identically_so_nothing_is_stored_twice():
    """Re-uploading the same export: every record hashes to the value already stored, so the
    writer skips it — and an unchanged universe gets no new books."""
    records = [ParsedRecord(text="tickets book pannitten", timestamp=datetime(2025, 3, 10, 9), author="Rahul"),
               ParsedRecord(text="ok", timestamp=datetime(2025, 3, 10, 9), author="Maaz"),
               ParsedRecord(text="ok", timestamp=datetime(2025, 3, 10, 9), author="Maaz")]  # a genuine repeat
    first, second = content_hashes("chat-fp", records), content_hashes("chat-fp", list(records))
    assert first == second and len(set(first)) == 3


def test_pages_already_in_a_book_only_mark_it_as_grown_and_never_move():
    trip = book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {RAHUL: 60}, TRIP_TOPIC)
    grown = page(date(2025, 3, 12), TRIP_CHAT, {RAHUL: 3}, TRIP_TOPIC, event_id=trip.id)
    plan = plan_books([grown], [trip])
    assert plan.assignments == {} and plan.new_books == []
    assert plan.touched_book_ids == {trip.id} and plan.updated_book_ids == {trip.id}


def test_nothing_new_means_no_changes():
    plan = plan_books([], [book(date(2025, 3, 10), date(2025, 3, 14), TRIP_CHAT, {}, TRIP_TOPIC)])
    assert (plan.new_books, plan.assignments, plan.touched_book_ids) == ([], {}, set())


def test_planning_is_deterministic():
    pages = [page(date(2024, 6, 1) + timedelta(days=i % 9), [TRIP_CHAT, WORK_CHAT][i % 2],
                  {[RAHUL, MANAGER][i % 2]: 5}, [TRIP_TOPIC, WORK_TOPIC][i % 2]) for i in range(18)]
    first = plan_books(pages, [], new_id=sequential_ids())
    second = plan_books(list(reversed(pages)), [], new_id=sequential_ids())  # input order must not matter
    assert first.assignments == second.assignments
    assert [b.position for b in first.new_books] == [b.position for b in second.new_books]


# ---- stable visual positioning ---------------------------------------------------------------------

def test_positions_are_deterministic_and_on_the_time_river():
    start = datetime(2025, 3, 10, 12, tzinfo=UTC)
    a, b = layout.place_book(start, RAHUL, []), layout.place_book(start, RAHUL, [])
    assert a == b
    assert a[0] == layout.time_x(date(2025, 3, 10)) == (date(2025, 3, 10) - layout.ORIGIN).days * layout.UNITS_PER_DAY
    other_lane = layout.place_book(start, PRIYA, [])
    assert math.isclose(math.hypot(a[1], a[2]), math.hypot(*other_lane[1:]), abs_tol=1e-3)  # same ring…
    assert (a[1], a[2]) != other_lane[1:]  # …at another angle
    assert layout.lane_angle(RAHUL) == layout.lane_angle(RAHUL) != layout.lane_angle(PRIYA)


def test_a_new_book_never_overlaps_and_never_moves_existing_books():
    existing = [book(date(2025, 3, 10), date(2025, 3, 12), TRIP_CHAT, {RAHUL: 5}, TRIP_TOPIC, lane=RAHUL)]
    before = [b.position for b in existing]
    same_day_same_lane = page(date(2025, 3, 10), NEW_CHAT, {RAHUL: 2}, NEW_TOPIC)  # would sit exactly on top
    plan = plan_books([same_day_same_lane], existing)
    assert [b.position for b in existing] == before  # existing books keep their place
    new = plan.new_books[0].position
    assert math.dist(new, existing[0].position) >= layout.MIN_SPACING


def test_uploading_older_memories_later_does_not_shift_anything():
    """The origin is a fixed date, not 'your oldest memory', so older data lands further left."""
    x_before = layout.time_x(date(2025, 3, 10))
    layout.place_book(datetime(2012, 1, 1, tzinfo=UTC), RAHUL, [])  # an old chat arrives
    assert layout.time_x(date(2025, 3, 10)) == x_before


# ---- relationship creation (graph) ----------------------------------------------------------------

def test_new_upload_connects_a_person_to_an_earlier_book():
    """Person A ├── Andhra Trip (new) └── Old Trip (existing) → 'New connection discovered'."""
    old_trip, andhra = str(uuid.uuid4()), str(uuid.uuid4())
    links = graph.new_person_links({RAHUL: {old_trip}}, {andhra: {RAHUL, PRIYA}})
    assert len(links) == 1  # Priya had no earlier book: nothing to connect
    assert (links[0].person_id, links[0].book_id, links[0].other_book_ids) == (RAHUL, andhra, [old_trip])


def test_a_book_growing_with_people_already_in_it_is_not_a_new_connection():
    trip = str(uuid.uuid4())
    assert graph.new_person_links({RAHUL: {trip}}, {trip: {RAHUL}}) == []


# ---- titles (never invent) ------------------------------------------------------------------------

def test_date_ranges_read_naturally():
    assert titles.format_range(date(2024, 6, 14), date(2024, 6, 14)) == "14 Jun 2024"
    assert titles.format_range(date(2024, 6, 12), date(2024, 6, 18)) == "12–18 Jun 2024"
    assert titles.format_range(date(2024, 6, 28), date(2024, 7, 3)) == "28 Jun – 3 Jul 2024"
    assert titles.format_range(date(2024, 12, 28), date(2025, 1, 2)) == "28 Dec 2024 – 2 Jan 2025"


def test_auto_titles_use_only_names_and_dates():
    d = date(2024, 6, 14)
    assert titles.auto_title(["Rahul", "Priya"], [], d, d, False) == "Rahul & Priya · 14 Jun 2024"
    assert titles.auto_title(["A", "B", "C", "D"], [], d, d, False).startswith("A, B +2")
    assert titles.auto_title([], ["Journal 2024"], d, d, False).startswith("Journal 2024")
    assert titles.auto_title([], [], d, d, True).startswith("Photos")


def test_ai_places_are_kept_only_when_the_memories_name_them():
    texts = ["Vizag beach la sunrise paathom", "Araku valley ku train"]
    assert titles.grounded_places(["Vizag", "Araku valley", "Goa"], texts) == ["Vizag", "Araku valley"]


def test_samples_cover_the_whole_book_and_user_titles_are_never_overwritten():
    sample = titles.spread_sample(list(range(100)), 5)
    assert sample[0] == 0 and sample[-1] == 99 and len(sample) == 5
    renamed = SimpleNamespace(title_source="user", memory_count=500, summarized_count=0)
    fresh = SimpleNamespace(title_source="auto", memory_count=50, summarized_count=0)
    grown = SimpleNamespace(title_source="ai", memory_count=160, summarized_count=100)
    unchanged = SimpleNamespace(title_source="ai", memory_count=120, summarized_count=100)
    assert [titles.needs_ai_title(b) for b in (renamed, fresh, grown, unchanged)] == [False, True, True, False]


# ---- universe update (change feed) ----------------------------------------------------------------

def test_change_feed_describes_new_books_grown_books_and_connections():
    user_id, created, grown = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = changes.describe(
        user_id, None,
        [BookChange(created, "Newly discovered", True, 0, 120, 0, 3, {}),
         BookChange(grown, "Andhra Trip", False, 300, 380, 5, 7, {RAHUL: 10})],
        [graph.PersonLink(RAHUL, str(grown), ["old-trip"])], [],
        names={RAHUL: "Rahul"}, titles={str(grown): "Andhra Trip", "old-trip": "Old Trip"},
        totals={"books_created": 1})
    kinds = [row.kind for row in rows]
    assert kinds == ["book_created", "book_grown", "connection", "update"]
    assert rows[1].detail["added_memories"] == 80 and rows[1].detail["added_pages"] == 2
    assert rows[2].detail["person"] == "Rahul" and rows[2].detail["other_books"][0]["title"] == "Old Trip"


def test_a_huge_first_build_does_not_flood_the_feed():
    many = [BookChange(uuid.uuid4(), f"Book {i}", True, 0, 10, 0, 1, {}) for i in range(500)]
    rows = changes.describe(uuid.uuid4(), None, many, [], [], {}, {}, {"books_created": 500})
    assert len(rows) == changes.MAX_ROWS_PER_UPDATE + 1 and rows[-1].kind == "update"


# ---- pipeline: incremental embedding and the universe step ----------------------------------------

async def test_pipeline_embeds_only_new_memories_then_updates_the_universe(monkeypatch):
    import app.ingestion.pipeline as pipeline

    calls: list[tuple] = []
    new_batches = iter([[uuid.uuid4(), uuid.uuid4()], []])  # first upload: 2 new; re-upload: all duplicates

    class Storage:
        async def get(self, key):
            return b"chat"

    async def insert_memories(session, job, source, conversation_id, result, resolver, on_progress):
        ids = next(new_batches)
        return ids, Counter(total=2, new=len(ids), skipped=2 - len(ids))

    async def embed_memories(session, ids, job=None):
        calls.append(("embed", list(ids)))
        return len(ids)

    async def update_universe(session, user_id, job_id):
        calls.append(("universe", job_id))
        from app.universe.updater import UniverseStats
        return UniverseStats(memories_placed=2, books_created=1, new_book_ids=[str(uuid.UUID(int=5))])

    async def name_books(user_id, prefer):
        calls.append(("titles", prefer))
        return 0

    async def noop(*args, **kwargs):
        return 0

    async def conversation(*args, **kwargs):
        return uuid.uuid4()

    async def source(*args, **kwargs):
        return SimpleNamespace(id=uuid.uuid4(), last_processed_at=None)

    result = SimpleNamespace(records=[object()], conversation_title="Andhra trip")
    for name, value in {
        "get_storage": lambda: Storage(), "parse_upload": lambda *a: SimpleNamespace(results=[result], media=[]),
        "upsert_source": source, "get_or_create_conversation": conversation, "insert_memories": insert_memories,
        "build_conversation_edges": noop, "embed_memories": embed_memories, "learn_from_memories": noop,
        "analyze_memories": noop, "update_universe": update_universe, "name_books": name_books,
        "_self_names": noop, "PersonResolver": lambda *a: None,
    }.items():
        monkeypatch.setattr(pipeline, name, value)

    class Session:
        async def commit(self):
            pass

        async def rollback(self):
            pass

    job = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), object_key="k", filename="chat.txt",
                          source_type="whatsapp", source_id=None, options={}, progress=0.0, stats={})
    first = await pipeline.run_ingestion(Session(), job)
    second = await pipeline.run_ingestion(Session(), job)

    embeds = [args for kind, args in calls if kind == "embed"]
    assert len(embeds[0]) == 2 and embeds[1] == []  # only new memories are embedded; duplicates cost nothing
    kinds = [kind for kind, _ in calls]
    assert kinds.index("embed") < kinds.index("universe") < kinds.index("titles")  # books see the new vectors
    assert first["universe"]["books_created"] == 1 and "new_book_ids" not in first["universe"]
    assert second["skipped"] == 2 and second["new"] == 0


async def test_a_failing_universe_update_never_fails_the_import(monkeypatch):
    import app.ingestion.pipeline as pipeline

    async def broken(*args, **kwargs):
        raise RuntimeError("database hiccup")

    rolled_back = []

    class Session:
        async def rollback(self):
            rolled_back.append(True)

    monkeypatch.setattr(pipeline, "update_universe", broken)
    job = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    assert await pipeline._update_universe_safely(Session(), job) is None and rolled_back


# ---- SQL compiles against PostgreSQL ---------------------------------------------------------------

class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)

    def scalars(self):
        return Rows([row[0] if isinstance(row, tuple) else row for row in self.rows])

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class RecordingSession:
    """Renders every statement to PostgreSQL SQL; returns canned rows for statements containing a marker."""

    def __init__(self, canned: dict[str, list] | None = None):
        self.sql: list[str] = []
        self.canned = canned or {}

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement.compile(dialect=POSTGRES))
        self.sql.append(sql)
        for marker, rows in self.canned.items():
            if marker in sql:
                return Rows(rows)
        return Rows()

    async def scalar(self, statement):
        await self.execute(statement)
        return 0

    async def get(self, *args):
        return None


async def test_universe_queries_compile():
    from app.retrieval.books import book_search
    from app.retrieval.query import SearchFilters
    from app.universe import books, pages

    user_id = uuid.uuid4()
    session = RecordingSession()
    key = pages.PageKey(TRIP_CHAT, date(2025, 3, 10), when(date(2025, 3, 10)), when(date(2025, 3, 10), 20))
    await pages.find_new_page_keys(session, user_id)
    await pages.place_memories(session, user_id, [key])
    await pages.refresh_pages(session, [uuid.uuid4()])
    await pages.page_item_counts(session, user_id)
    await books.load_nearby_books(session, user_id, date(2025, 3, 1), date(2025, 3, 20))
    await books.refresh_books(session, {uuid.uuid4()}, set())
    await graph.existing_appearances(session, user_id, [RAHUL])
    await graph.save_appearances(session, user_id, {str(uuid.uuid4()): {RAHUL: 3}})
    await book_search(session, [0.1] * 768, SearchFilters(user_id=user_id, start=when(date(2025, 1, 1))))
    joined = "\n".join(session.sql)
    assert "NOT (EXISTS" in joined  # unplaced = no memory_page_items row
    assert "ON CONFLICT (user_id, page_key) DO NOTHING" in joined
    assert "INSERT INTO memory_page_items" in joined and "concat(" in joined
    assert "avg(memories.embedding)" in joined  # page centroid from stored vectors — no re-embedding
    assert "timezone('Asia/Kolkata'" in joined  # pages are local calendar days
    assert "ON CONFLICT (user_id, src_type, src_id, rel_type, dst_type, dst_id, source_memory_id) DO UPDATE" in joined


async def test_related_books_come_from_vector_similarity_and_skip_the_same_period():
    book_id, far_away, same_week = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    start = datetime(2025, 3, 10, tzinfo=UTC)
    session = RecordingSession({
        "WHERE events.id IN": [(book_id, [0.1] * 768, start)],
        "ORDER BY events.centroid <=>": [(same_week, 0.95, start + timedelta(days=3)),
                                         (far_away, 0.9, start - timedelta(days=400))],
    })
    related = await graph.find_related_books(session, uuid.uuid4(), [book_id])
    assert [(r.book_id, r.other_id) for r in related] == [(book_id, far_away)]
    assert any("<=>" in sql for sql in session.sql)
