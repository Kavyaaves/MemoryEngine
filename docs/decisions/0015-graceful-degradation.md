# 0015. Every AI step has a fallback that needs no AI

- **Status:** Accepted

## Context

AI calls fail: the key is missing, the quota is used up, OpenAI is down or rate-limiting. A memory
app that shows an error page whenever the AI is unavailable is useless at exactly those moments.

## Decision

Each AI step has a deterministic fallback, and the router raises one error type (`AIUnavailable`)
that callers catch:

| AI step | Without AI |
|---|---|
| Understanding the question | rule-based `heuristic_analysis()` |
| Semantic search | keyword, fuzzy, graph and temporal paths still run |
| LLM reranking | the heuristic order |
| Verifying evidence | accept what was found |
| Writing the answer | `extractive_answer()`: the matching memories with citations |

Answers made this way are flagged `degraded: true`, and the UI says so.

## Consequences

- The app works with no API key at all, which also makes tests easy (no keys needed).
- Each fallback has to be maintained and tested alongside its AI step.

## Where in the code

`backend/app/ai/providers/base.py` (`AIUnavailable`), `agents/query_analysis.py`,
`agents/answering.py`, `retrieval/reranker.py`.
