# 0027. Measure retrieval on your own data, one step at a time

- **Status:** Accepted

## Context

Every retrieval choice (fusion weights, the LLM reranker, MMR, the similarity cut-off) is a guess
until it is measured. Public benchmarks don't contain Tanglish WhatsApp chats, so only the user's own
data can tell whether a change helped.

## Decision

- `golden_builder` writes a test set from the user's own memories: about 150 questions in English,
  Tanglish and search-box style, each pointing at the memory that answers it. The user reads it and
  deletes bad questions. It quotes private messages, so it stays out of git (`eval/*.jsonl`).
- `runner` compares pipelines where **each row adds one step**: keyword → vector → hybrid →
  heuristic rerank → LLM rerank → MMR. The table shows what each step is worth.
- Metrics: hit rate@K, Recall@K, MRR, NDCG and latency. `--answers` also runs the full agent and has
  an LLM judge grade every answer. RAGAS is available with the `.[eval]` extra.
- `cache_benchmark` measures prompt caching ([0017](0017-prompt-caching.md)).
- Reports go to `backend/eval/results/` as Markdown and JSON.

## Consequences

- Tuning is evidence-based: change a setting, re-run, compare the table.
- A full run calls OpenAI and costs cents.

## Where in the code

`backend/app/evaluation/` (`golden_builder.py`, `runner.py`, `metrics.py`, `report.py`,
`cache_benchmark.py`), `backend/README.md#measuring-quality-evaluation`. PLAN.md §36–37.
