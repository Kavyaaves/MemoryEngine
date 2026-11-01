"""Book search path — the Graph RAG part of retrieval (PLAN §12, app/universe/).

Plain vector search compares the question with single messages, and a short chat message
("same", "ok da") says little on its own. Memory Books group messages into events, so:

    1. global step: find the TOP_BOOKS books whose average meaning is closest to the question
       ("what happened on the Andhra trip?" → the Andhra Trip book)
    2. local step:  inside those books, return the memories closest to the question

The candidates are fused with the other paths (fts, trgm, vector, graph, temporal) as path
"book". The agent also shows the answer model a short, clearly labelled summary of the books
the evidence comes from (see agents/tools.py event_context) — context, never evidence.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, Memory, MemoryPage, MemoryPageItem
from app.retrieval.query import Candidate, SearchFilters

TOP_BOOKS = 3
MIN_BOOK_SIMILARITY = 0.3  # a book less similar than this to the question isn't worth searching inside


async def book_search(session: AsyncSession, query_vector: list[float] | None, filters: SearchFilters,
                      limit: int = 50) -> list[Candidate]:
    if query_vector is None:
        return []
    book_distance = Event.centroid.cosine_distance(query_vector)
    books_query = select(Event.id, book_distance).where(Event.user_id == filters.user_id, Event.centroid.is_not(None))
    if filters.start:
        books_query = books_query.where(Event.end_at >= filters.start)
    if filters.end:
        books_query = books_query.where(Event.start_at < filters.end)
    books = [(book_id, 1.0 - float(d)) for book_id, d in
             (await session.execute(books_query.order_by(book_distance).limit(TOP_BOOKS))).all()]
    book_ids = [book_id for book_id, similarity in books if similarity >= MIN_BOOK_SIMILARITY]
    if not book_ids:
        return []

    settings = get_settings()
    distance = Memory.embedding.cosine_distance(query_vector)
    in_books = select(MemoryPageItem.memory_id).join(MemoryPage, MemoryPage.id == MemoryPageItem.page_id) \
        .where(MemoryPage.event_id.in_(book_ids))
    query = select(Memory.id, distance).where(Memory.id.in_(in_books), Memory.embedding.is_not(None),
                                              Memory.embedding_model == settings.embedding_model)
    rows = await session.execute(filters.apply(query).order_by(distance).limit(limit))

    floor = settings.vector_min_similarity  # same noise floor and 0..1 rescaling as the vector path
    return [Candidate(memory_id, (1.0 - float(d) - floor) / (1.0 - floor), "book")
            for memory_id, d in rows.all() if 1.0 - float(d) >= floor]
