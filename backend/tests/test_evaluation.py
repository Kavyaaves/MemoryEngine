"""Evaluation tools: metrics, dataset lines, reports and the cache benchmark's prompts (no database or API)."""

import random

import pytest

from app.ai.prompts import ANSWER_SYSTEM
from app.evaluation import cache_benchmark, runner
from app.evaluation.golden_builder import STYLES, dataset_line, question_prompt
from app.evaluation.metrics import aggregate, hit_rate_at_k, percentile
from app.evaluation.report import markdown_table, write_report
from app.schemas.ai import GeneratedQuestion


def test_hit_rate_counts_a_question_as_found_if_any_relevant_memory_is_in_the_top_k():
    assert hit_rate_at_k(["a", "b", "c"], {"c", "z"}, 3) == 1.0
    assert hit_rate_at_k(["a", "b", "c"], {"c"}, 2) == 0.0


def test_percentiles_and_aggregate():
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([5], 95) == 5 and percentile([], 50) == 0.0
    summary = aggregate([{"mrr": 1.0, "latency_ms": 100.0}, {"mrr": 0.5, "latency_ms": 300.0}])
    assert summary["mrr"] == 0.75 and summary["latency_p50_ms"] == 200.0 and summary["n"] == 2


def test_every_pipeline_is_a_valid_search_configuration():
    for name, options in runner.PIPELINES.items():
        assert options["mode"] in {"hybrid", "fts", "trgm", "vector", "graph"}, name
        assert options["reranker"] in {"none", "heuristic", "llm"}, name
    assert set(runner.DEFAULT_PIPELINES.split(",")) <= set(runner.PIPELINES)


def test_retrieval_scores_for_one_question():
    scores = runner.retrieval_scores(["x", "rel"], {"rel": 1.0}, k=10, latency_ms=12.0)
    assert scores == {"hit_rate@10": 1.0, "recall@10": 1.0, "mrr": 0.5, "ndcg@10": pytest.approx(0.6309, abs=1e-4),
                      "latency_ms": 12.0}


def test_generated_questions_point_at_the_memory_they_came_from():
    prompt = question_prompt("Booked the Kerala train for the 28th", "Rahul", "2024-06-14", "whatsapp", "tanglish")
    assert "Rahul" in prompt and "2024-06-14" in prompt and STYLES["tanglish"] in prompt
    line = dataset_line(3, "english", "h" * 64, "Booked the Kerala train",
                        GeneratedQuestion(usable=True, question=" when did we book the train? ",
                                          reference_answer="On 14 June 2024."))
    assert line == {"id": "gen-3", "category": "english", "question": "when did we book the train?",
                    "relevant": ["h" * 64], "reference_answer": "On 14 June 2024.",
                    "source_preview": "Booked the Kerala train"}


def test_report_is_rendered_and_saved(tmp_path):
    metrics = {"hit_rate@10": 0.8, "recall@10": 0.8, "mrr": 0.61, "ndcg@10": 0.66, "latency_ms": 90.0,
               "latency_p50_ms": 85.0, "latency_p95_ms": 140.0, "n": 5}
    report = {"dataset": "eval/golden.jsonl", "questions": 5, "settings": {"prompt_version": "x"},
              "retrieval": {"k": 10, "by_pipeline": {"vector": metrics, "hybrid+llm": metrics},
                            "by_category": {"vector/english": metrics, "vector/tanglish": metrics},
                            "skipped_no_relevant_memory": []}}
    markdown = runner.render_markdown(report)
    assert "| hybrid+llm | 80.0% | 80.0% | 0.610 | 0.660 | 85 | 140 |" in markdown
    assert "english" in markdown and "tanglish" in markdown
    markdown_path, json_path = write_report("test", markdown, report, results_dir=tmp_path)
    assert markdown_path.read_text(encoding="utf-8") == markdown and json_path.exists()
    assert markdown_table(["a"], [[1]]) == "| a |\n|---|\n| 1 |"


def test_cache_benchmark_keeps_the_system_prompt_first_and_varies_the_rest():
    rng = random.Random(1)
    first, second = cache_benchmark.answer_messages(ANSWER_SYSTEM, rng), cache_benchmark.answer_messages(ANSWER_SYSTEM, rng)
    assert first[0] == second[0] == ("system", ANSWER_SYSTEM)  # the cacheable part is identical
    assert first[1] != second[1]  # the evidence and question differ, as in real use
    assert first[1][1].count("<memory ") == cache_benchmark.EVIDENCE_MEMORIES
