"""Measure retrieval and answer quality against a golden dataset (PLAN §36–37).

Dataset: a JSONL file, one question per line (lines starting with // are comments). Make one
from your own memories with app.evaluation.golden_builder, or write it by hand:
    {"id": "q1", "question": "naan avan kooda pona trip", "category": "tanglish",
     "relevant": ["<memory uuid or content_hash>", ...],       # or {"<id>": grade} for graded relevance
     "reference_answer": "optional — needed for --answers and --ragas"}

Run (from backend/):
    python -m app.evaluation.runner --user you@example.com --dataset eval/golden.jsonl
    python -m app.evaluation.runner ... --pipelines vector,hybrid+llm --answers

1. Retrieval: every question is searched with each PIPELINE below. For each pipeline you get
   hit rate@k (share of questions with a relevant memory in the top k — "retrieval accuracy"),
   recall@k, MRR, NDCG@k and latency (p50/p95), overall and per category. The pipelines add
   one idea at a time, so the table shows what each step is worth.
2. --answers: runs the full agent on questions with a reference_answer and has the answer model
   grade each answer (correct / partial / wrong, and grounded in the evidence or not), plus the
   time until the first word of the answer arrived and the total time.
3. --ragas: the same answers scored by RAGAS (install with: pip install -e ".[eval]").

The report is written to eval/results/ (Markdown + JSON). Searches here get only the question —
not the people, dates or rewrites the agent would add — so the graph and temporal paths stay off.
"""

import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.agents.answering import format_evidence
from app.ai.prompts import ANSWER_JUDGE_SYSTEM
from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import AIRouter, get_router
from app.db import SessionLocal
from app.evaluation.metrics import aggregate, hit_rate_at_k, mrr, ndcg_at_k, percentile, recall_at_k
from app.evaluation.report import markdown_table, percent, run_settings, write_report
from app.models import Memory, User
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.query import SearchFilters
from app.schemas.ai import AnswerVerdict

# Each pipeline adds one idea to the one before it.
PIPELINES: dict[str, dict] = {
    "keyword": {"mode": "fts", "reranker": "none"},  # full-text search alone
    "vector": {"mode": "vector", "reranker": "none"},  # semantic (embedding) search alone
    "hybrid": {"mode": "hybrid", "reranker": "none"},  # all paths, merged with RRF
    "hybrid+heuristic": {"mode": "hybrid", "reranker": "heuristic"},
    "hybrid+llm": {"mode": "hybrid", "reranker": "llm"},  # the app's default
    "hybrid+llm+mmr": {"mode": "hybrid", "reranker": "llm", "mmr_lambda": 0.7},
}
DEFAULT_PIPELINES = "keyword,vector,hybrid,hybrid+heuristic,hybrid+llm,hybrid+llm+mmr"
CORRECTNESS_POINTS = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}


def load_dataset(path: str | Path) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip() and not line.lstrip().startswith("//")]


async def _relevant_memory_ids(session, user_id: uuid.UUID, relevant) -> dict[str, float]:
    """Dataset references (uuids or 64-char content hashes) → {memory uuid: relevance grade}."""
    grades = relevant if isinstance(relevant, dict) else {ref: 1.0 for ref in relevant}
    by_uuid = {str(uuid.UUID(ref)): float(g) for ref, g in grades.items() if len(ref) != 64}
    hashes = [ref for ref in grades if len(ref) == 64]
    if hashes:
        rows = await session.execute(select(Memory.content_hash, Memory.id).where(
            Memory.user_id == user_id, Memory.content_hash.in_(hashes)))
        for content_hash, memory_id in rows.all():
            by_uuid[str(memory_id)] = float(grades[content_hash])
    return by_uuid


def retrieval_scores(retrieved: list[str], relevant: dict[str, float], k: int, latency_ms: float) -> dict:
    return {f"hit_rate@{k}": hit_rate_at_k(retrieved, relevant, k), f"recall@{k}": recall_at_k(retrieved, relevant, k),
            "mrr": mrr(retrieved, relevant), f"ndcg@{k}": ndcg_at_k(retrieved, relevant, k),
            "latency_ms": latency_ms}


async def evaluate_retrieval(session, user: User, dataset: list[dict], pipelines: list[str], k: int,
                             router: AIRouter) -> dict:
    retriever = HybridRetriever(router)
    by_pipeline: dict[str, list[dict]] = defaultdict(list)
    by_category: dict[str, list[dict]] = defaultdict(list)
    details, skipped = [], []
    for number, item in enumerate(dataset, start=1):
        relevant = await _relevant_memory_ids(session, user.id, item["relevant"])
        if not relevant:  # e.g. the memory was deleted since the dataset was made
            skipped.append(item.get("id"))
            continue
        for name in pipelines:
            options = {"mmr_lambda": 1.0, **PIPELINES[name]}  # explicit, so .env settings don't leak in
            start = time.perf_counter()
            result = await retriever.search(session, item["question"], SearchFilters(user_id=user.id), k=k, **options)
            latency_ms = (time.perf_counter() - start) * 1000
            scores = retrieval_scores([str(e.memory_id) for e in result.evidence], relevant, k, latency_ms)
            by_pipeline[name].append(scores)
            by_category[f"{name}/{item.get('category', 'uncategorised')}"].append(scores)
            details.append({"id": item.get("id"), "pipeline": name, **scores})
        print(f"retrieval: {number}/{len(dataset)} questions")
    return {"k": k, "by_pipeline": {name: aggregate(rows) for name, rows in by_pipeline.items()},
            "by_category": {c: aggregate(rows) for c, rows in by_category.items()},
            "skipped_no_relevant_memory": skipped, "details": details}


async def judge_answer(router: AIRouter, item: dict, answer: str, evidence_block: str, user_id) -> AnswerVerdict | None:
    try:
        return await router.structured("reasoning", AnswerVerdict, [
            ("system", ANSWER_JUDGE_SYSTEM),
            ("user", f"Question: {item['question']}\n\nReference answer: {item['reference_answer']}\n\n"
                     f"Evidence shown to the assistant:\n{evidence_block}\n\nAssistant's answer:\n{answer}")],
            user_id=user_id)
    except AIUnavailable:
        return None


class FirstTokenClock:
    """Receives the agent's progress events and notes when the first word of the answer arrived."""

    def __init__(self):
        self.start = time.perf_counter()
        self.first_token_at: float | None = None

    async def emit(self, event: str, _data) -> None:
        if event == "token" and self.first_token_at is None:
            self.first_token_at = time.perf_counter()

    def first_token_ms(self) -> float | None:
        return None if self.first_token_at is None else (self.first_token_at - self.start) * 1000


async def evaluate_answers(session, user: User, dataset: list[dict], router: AIRouter) -> dict:
    """Run the full agent on each question with a reference answer, then grade the answer."""
    from app.agents.graph import run_agent
    from app.agents.tools import MemoryTools

    rows = []
    items = [item for item in dataset if item.get("reference_answer")]
    for number, item in enumerate(items, start=1):
        clock = FirstTokenClock()
        tools = MemoryTools(session, user.id, HybridRetriever(router))
        result = await run_agent(question=item["question"], history=[], tools=tools, router=router, emit=clock.emit)
        total_ms = (time.perf_counter() - clock.start) * 1000
        verdict = await judge_answer(router, item, result["answer"], format_evidence(result["evidence"]), user.id)
        if verdict is None:
            continue
        rows.append({"id": item.get("id"), "category": item.get("category", "uncategorised"),
                     "correctness": verdict.correctness, "grounded": verdict.grounded,
                     "explanation": verdict.explanation, "degraded": result["trace"]["degraded"],
                     "total_ms": total_ms, "first_token_ms": clock.first_token_ms() or total_ms})
        print(f"answers: {number}/{len(items)} graded")
    if not rows:
        return {"error": "no dataset items have a reference_answer, or the judge model was unavailable"}
    return {"n": len(rows),
            "accuracy": round(sum(CORRECTNESS_POINTS[r["correctness"]] for r in rows) / len(rows), 4),
            "grounded_rate": round(sum(r["grounded"] for r in rows) / len(rows), 4),
            "first_token_p50_ms": round(percentile([r["first_token_ms"] for r in rows], 50), 1),
            "total_p50_ms": round(percentile([r["total_ms"] for r in rows], 50), 1),
            "total_p95_ms": round(percentile([r["total_ms"] for r in rows], 95), 1),
            "details": rows}


async def evaluate_answers_with_ragas(session, user: User, dataset: list[dict]) -> dict:
    """Faithfulness, context precision/recall and answer relevancy, judged by OpenAI via RAGAS."""
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy

    from app.agents.graph import run_agent
    from app.agents.tools import MemoryTools
    from app.config import get_settings

    settings = get_settings()
    ai_router = get_router()
    samples = []
    for item in dataset:
        if not item.get("reference_answer"):
            continue
        tools = MemoryTools(session, user.id, HybridRetriever(ai_router))
        result = await run_agent(question=item["question"], history=[], tools=tools, router=ai_router)
        samples.append({"user_input": item["question"], "response": result["answer"],
                        "retrieved_contexts": [e.text for e in result["evidence"]],
                        "reference": item["reference_answer"]})
    if not samples:
        return {"error": "no dataset items have a reference_answer"}

    judge = LangchainLLMWrapper(ChatOpenAI(model=settings.openai_reasoning_model, api_key=settings.openai_api_key,
                                           temperature=0.0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=settings.openai_embedding_model,
                                                             api_key=settings.openai_api_key))
    scores = evaluate(EvaluationDataset.from_list(samples),
                      metrics=[Faithfulness(), LLMContextPrecisionWithReference(), LLMContextRecall(),
                               ResponseRelevancy()], llm=judge, embeddings=embeddings)
    means = scores.to_pandas().mean(numeric_only=True)
    return {"n": len(samples), "scores": {name: round(float(value), 4) for name, value in means.items()}}


def render_markdown(report: dict) -> str:
    k = report["retrieval"]["k"]
    lines = [f"# Evaluation — {report['dataset']}", "",
             f"{report['questions']} questions, top {k} results. Settings: `{json.dumps(report['settings'])}`", "",
             "## Retrieval by pipeline", ""]
    rows = []
    for name, m in report["retrieval"]["by_pipeline"].items():
        rows.append([name, percent(m[f"hit_rate@{k}"]), percent(m[f"recall@{k}"]), f"{m['mrr']:.3f}",
                     f"{m[f'ndcg@{k}']:.3f}", f"{m['latency_p50_ms']:.0f}", f"{m['latency_p95_ms']:.0f}"])
    lines.append(markdown_table(["pipeline", f"hit rate@{k}", f"recall@{k}", "MRR", f"NDCG@{k}",
                                 "p50 ms", "p95 ms"], rows))

    categories = sorted({c.split("/", 1)[1] for c in report["retrieval"]["by_category"]})
    pipelines = list(report["retrieval"]["by_pipeline"])
    if len(categories) > 1:
        lines += ["", f"## Hit rate@{k} by category", ""]
        table = []
        for name in pipelines:
            cells = []
            for category in categories:
                m = report["retrieval"]["by_category"].get(f"{name}/{category}")
                cells.append(f"{percent(m[f'hit_rate@{k}'])} (n={m['n']})" if m else "–")
            table.append([name, *cells])
        lines.append(markdown_table(["pipeline", *categories], table))

    answers = report.get("answers")
    if answers and "error" not in answers:
        lines += ["", "## Answers (full agent, graded by the answer model)", "",
                  markdown_table(["n", "accuracy", "grounded", "first word p50 ms", "total p50 ms", "total p95 ms"],
                                 [[answers["n"], percent(answers["accuracy"]), percent(answers["grounded_rate"]),
                                   f"{answers['first_token_p50_ms']:.0f}", f"{answers['total_p50_ms']:.0f}",
                                   f"{answers['total_p95_ms']:.0f}"]])]
    if report["retrieval"]["skipped_no_relevant_memory"]:
        lines += ["", f"Skipped (relevant memory no longer exists): {report['retrieval']['skipped_no_relevant_memory']}"]
    return "\n".join(lines) + "\n"


async def main(args: argparse.Namespace) -> dict:
    dataset = load_dataset(args.dataset)
    pipelines = [name.strip() for name in args.pipelines.split(",") if name.strip()]
    unknown = [name for name in pipelines if name not in PIPELINES]
    if unknown:
        raise SystemExit(f"unknown pipeline(s) {unknown}; choose from {list(PIPELINES)}")
    router = get_router()
    report = {"dataset": str(args.dataset), "questions": len(dataset), "settings": run_settings()}
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == args.user.lower()))).scalar_one()
        report["retrieval"] = await evaluate_retrieval(session, user, dataset, pipelines, args.k, router)
        if args.answers:
            report["answers"] = await evaluate_answers(session, user, dataset, router)
        if args.ragas:
            report["ragas"] = await evaluate_answers_with_ragas(session, user, dataset)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", required=True, help="email of the account whose memories to evaluate")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--pipelines", default=DEFAULT_PIPELINES, help=f"comma-separated, from: {', '.join(PIPELINES)}")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--answers", action="store_true", help="also run the agent and grade its answers")
    parser.add_argument("--ragas", action="store_true")
    arguments = parser.parse_args()

    results = asyncio.run(main(arguments))  # one event loop for the whole run
    markdown = render_markdown(results)
    print(markdown)
    markdown_path, json_path = write_report("eval", markdown, results)
    print(f"saved {markdown_path} and {json_path}")
