# 0008. Rerank in stages: heuristic, then LLM, then optional MMR

- **Status:** Accepted

## Context

RRF gives a good candidate list, but the order inside it is rough. A model reading each passage
judges relevance best, but it costs a call per question, so it should only see the best few.

## Decision

The merged candidates are re-ordered in up to three stages, chosen with `RERANKER` and `MMR_LAMBDA`:

1. **Heuristic** (always on, unless `RERANKER=none`). Cheap, deterministic signals: the RRF score,
   share of question words present, exact phrase match, how many paths agreed, vector similarity,
   and a penalty for tiny messages like "ok".
2. **LLM** (`RERANKER=llm`, the default). The fast model reads the top 20 passages (500 characters
   each) and scores each 0–10. Its score then dominates and the heuristic only breaks ties. This
   catches meaning the keyword signals miss, such as a Tanglish question matching a Tamil-script message.
3. **MMR diversity** (optional). Maximal Marginal Relevance pushes near-duplicates (the same
   forwarded message) down. `MMR_LAMBDA=1.0` turns it off. Try 0.7.

## Consequences

- If no model is reachable, the heuristic order is kept and search still works.
- `RERANKER=none` exists only as an evaluation baseline.
- The LLM scores also let the agent skip its verify call when a passage scored 8/10 or higher.

## Where in the code

`backend/app/retrieval/reranker.py`, `retrieval/diversity.py`, `config/settings.py` (`reranker`, `mmr_lambda`).
