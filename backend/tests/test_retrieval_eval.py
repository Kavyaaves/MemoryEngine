import uuid
from datetime import date

import pytest
from sqlalchemy.dialects import postgresql

from app.agents.query_analysis import parse_time_window, temporal_order
from app.evaluation.metrics import mrr, ndcg_at_k, recall_at_k
from app.people.aliases import alias_similarity, best_matches, normalize_alias
from app.retrieval.fusion import rrf_fuse
from app.retrieval.query import Candidate, keyword_query


def test_rrf_rewards_agreement_across_paths():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = rrf_fuse({
        "fts": [Candidate(a, 1, "fts"), Candidate(b, 1, "fts")],
        "vector": [Candidate(b, 1, "vector"), Candidate(c, 1, "vector")],
    }, k=60, weights={"fts": 1, "vector": 1})
    assert fused[0].memory_id == b
    assert set(fused[0].paths) == {"fts", "vector"}


def test_rrf_ignores_duplicate_candidates_within_a_path():
    a = uuid.uuid4()
    fused = rrf_fuse({"trgm": [Candidate(a, 1, "trgm"), Candidate(a, 0.9, "trgm")]}, weights={"trgm": 1})
    assert len(fused) == 1 and fused[0].score == pytest.approx(1 / 61)


def test_keyword_query_drops_stopwords_and_unsafe_tokens():
    compiled = keyword_query(["the", "kerala", "trip", "it's", "o'brien"]).compile(dialect=postgresql.dialect())
    assert "'kerala' | 'trip'" in compiled.params.values()
    assert keyword_query(["the", "a"]) is None


def test_metrics():
    got = ["a", "b", "c", "d"]
    assert recall_at_k(got, {"b", "z"}, 3) == 0.5
    assert mrr(got, {"c"}) == pytest.approx(1 / 3)
    assert ndcg_at_k(got, {"a"}, 3) == 1.0
    assert 0 < ndcg_at_k(got, {"c": 2.0, "a": 1.0}, 3) < 1


def test_temporal_parsing():
    today = date(2026, 9, 24)
    assert parse_time_window("messages from January 2024", today) == (date(2024, 1, 1), date(2024, 2, 1))
    assert parse_time_window("what happened in 2023?", today) == (date(2023, 1, 1), date(2024, 1, 1))
    assert parse_time_window("last year trips", today) == (date(2025, 1, 1), date(2026, 1, 1))
    assert parse_time_window("between 2021 and 2022", today) == (date(2021, 1, 1), date(2023, 1, 1))
    assert parse_time_window("after 2020", today) == (date(2021, 1, 1), None)
    assert parse_time_window("since 2020", today) == (date(2020, 1, 1), None)
    assert parse_time_window("nethu enna aachu", today) == (date(2026, 9, 23), today)
    assert parse_time_window("hello", today) == (None, None)
    assert temporal_order("When did I first say I love you?") == "first"
    assert temporal_order("Naan Rahul kooda first enga pona?") == "first"
    assert temporal_order("last message from amma") == "last"
    assert temporal_order("kerala trip") is None


def test_alias_normalisation_and_similarity():
    assert normalize_alias("Rahul ❤\ufe0f") == "rahul"  # emoji + variation selector removed
    assert normalize_alias("நான்") == "நான்"  # Tamil vowel signs are kept
    assert alias_similarity("rahul", normalize_alias("Rahul ❤")) == 1.0
    assert 0.8 <= alias_similarity("rahu", "rahul") < 1.0
    assert alias_similarity("r", "rahul") == 0.75
    assert alias_similarity("r", "priya") == 0.0
    assert alias_similarity("+91 98765 43210", "+91 98765 43211") == 0.0


def test_best_matches_only_suggests_plausible_people():
    rahul, priya = uuid.uuid4(), uuid.uuid4()
    known = {"rahul": rahul, "priya": priya}
    assert [person_id for person_id, _ in best_matches("Rahu", known)] == [rahul]
    assert best_matches("Karthik", known) == []
