"""Compile every query and the schema DDL against the PostgreSQL dialect.

No database server is needed: a fake session records each statement and renders it, which
catches SQLAlchemy construction errors (bad operators, joins, JSONB paths, vector ops).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401 - registers every table
from app.ai.providers.router import AIRouter
from app.ai.usage import UsageManager
from app.config import Settings
from app.core.timeutils import local_period
from app.db import Base
from app.evaluation.golden_builder import sample_memories
from app.models import Memory
from app.retrieval.fusion import FusedCandidate
from app.retrieval.graph import graph_search, related_people, resolve_people
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.lexical import fts_count, fts_search, trgm_search
from app.retrieval.query import SearchFilters
from app.retrieval.temporal import temporal_search
from app.retrieval.vector import vector_search

POSTGRES = postgresql.dialect()


class _EmptyResult:
    def all(self):
        return []

    def scalars(self):
        return self

    def first(self):
        return None

    def scalar_one(self):
        return 0

    def scalar(self):
        return None


class _VersionResult(_EmptyResult):
    def __init__(self, version):
        self.version = version

    def scalar(self):
        return self.version


class FakeSession:
    def __init__(self):
        self.sql: list[str] = []
        self.version: str | None = None  # what "SELECT extversion ..." returns

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement.compile(dialect=POSTGRES))
        self.sql.append(sql)
        return _VersionResult(self.version) if "extversion" in sql else _EmptyResult()


def filters():
    return SearchFilters(user_id=uuid.uuid4(), start=datetime(2024, 1, 1, tzinfo=UTC),
                         end=datetime(2025, 1, 1, tzinfo=UTC), person_ids=[uuid.uuid4()], source_types=["whatsapp"])


def test_schema_ddl_compiles():
    for table in Base.metadata.sorted_tables:
        assert table.name in str(CreateTable(table).compile(dialect=POSTGRES))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=POSTGRES))
    memories = str(CreateTable(Base.metadata.tables["memories"]).compile(dialect=POSTGRES))
    assert "GENERATED ALWAYS AS (to_tsvector('simple'" in memories
    assert "VECTOR(768)" in memories
    indexes = {i.name: str(CreateIndex(i).compile(dialect=POSTGRES)) for i in Base.metadata.tables["memories"].indexes}
    assert "USING hnsw (embedding vector_cosine_ops)" in indexes["ix_memories_embedding_hnsw"]
    assert "gin_trgm_ops" in indexes["ix_memories_search_trgm"]
    relationships = str(CreateTable(Base.metadata.tables["relationships"]).compile(dialect=POSTGRES))
    assert "NULLS NOT DISTINCT" in relationships


async def test_lexical_queries_compile():
    session = FakeSession()
    await fts_search(session, ["kerala", "trip", "the"], filters())
    await fts_search(session, ["kerala"], filters(), order="asc")
    await fts_count(session, ["kerala"], filters())
    await trgm_search(session, "kooda pona", filters())
    joined = "\n".join(session.sql)
    assert "to_tsquery" in joined and "@@" in joined
    assert "count(*)" in joined
    assert "set_config" in joined and "word_similarity" in joined and "<%" in joined
    assert "memory_participants" in joined  # the person filter


async def test_vector_graph_temporal_queries_compile():
    session = FakeSession()
    await vector_search(session, [0.1] * 768, filters())
    await graph_search(session, ["trip"], [uuid.uuid4()], filters())
    await graph_search(session, [], [uuid.uuid4()], filters())
    await temporal_search(session, ["trip"], filters(), "first")
    await resolve_people(session, uuid.uuid4(), ["Rahul"])
    await related_people(session, uuid.uuid4(), uuid.uuid4())
    joined = "\n".join(session.sql)
    assert "<=>" in joined  # pgvector cosine distance
    assert "SELECT set_config(" in joined and "pg_extension" in joined  # the HNSW scan is widened
    assert "relationships" in joined


async def test_iterative_scan_is_only_turned_on_for_pgvector_0_8_and_newer(monkeypatch):
    import app.retrieval.vector as vector

    assert vector.parse_version("0.8.0") >= vector.ITERATIVE_SCAN_MIN_VERSION
    assert vector.parse_version("0.7.4") < vector.ITERATIVE_SCAN_MIN_VERSION
    assert vector.parse_version(None) == (0,) and vector.parse_version("abc") == (0,)

    for version, expected_settings in (("0.7.4", 1), ("0.8.0", 2)):
        monkeypatch.setattr(vector, "_iterative_scan_supported", None)  # forget the cached answer
        session = FakeSession()
        session.version = version
        await vector.vector_search(session, [0.1] * 768, filters())
        set_config_sql = next(sql for sql in session.sql if "set_config" in sql)
        assert set_config_sql.count("set_config(") == expected_settings


async def test_reranking_diversity_and_test_set_queries_compile():
    router = AIRouter([], UsageManager(Settings(), persist=False))  # no AI: the LLM stage is skipped
    pool = [FusedCandidate(uuid.uuid4(), 0.03, ["fts"]), FusedCandidate(uuid.uuid4(), 0.02, ["vector"])]
    session = FakeSession()
    ranked, llm_scores = await HybridRetriever(router)._rerank(session, pool, "kerala trip", ["kerala", "trip"],
                                                               filters(), reranker="llm", mmr_lambda=0.7)
    assert llm_scores == {}  # no AI → the LLM stage didn't run
    assert {memory_id for memory_id, _, _ in ranked} == {c.memory_id for c in pool}
    await sample_memories(session, uuid.uuid4(), count=5)
    joined = "\n".join(session.sql)
    assert "memories.author_raw" in joined  # the reranker shows the LLM who wrote each passage
    assert "memories.embedding IS NOT NULL" in joined  # MMR reads the stored vectors
    assert "random()" in joined and "length(memories.text) BETWEEN" in joined


def test_timeline_bucket_is_identical_in_select_and_group_by():
    """Constants are inlined, so PostgreSQL sees the same expression in SELECT and GROUP BY."""
    period = local_period(Memory.timestamp, "month")
    sql = str(select(period, func.count()).group_by(period).compile(dialect=POSTGRES))
    expression = "to_char(date_trunc('month', timezone('Asia/Kolkata', memories.timestamp)), 'YYYY-MM')"
    assert sql.count(expression) == 2
    assert "%(" not in sql and "$" not in sql  # no bind parameters
