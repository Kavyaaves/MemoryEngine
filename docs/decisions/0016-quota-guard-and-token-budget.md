# 0016. A quota guard: request caps, a token budget, and a usage log

- **Status:** Accepted

## Context

OpenAI is billed per token, and a bug or a big import could spend a lot quickly. One question uses
roughly 10,000 tokens (understand, rerank, verify, answer).

## Decision

- Before every call, the usage manager checks three limits:
  - `MAX_DAILY_REQUESTS` (default 1,500) and `MAX_MONTHLY_REQUESTS` (30,000), per provider
  - `MAX_TOKENS_PER_WINDOW` (default 2,000,000) every `TOKEN_WINDOW_HOURS` hours (default 24,
    resetting at midnight UTC). `0` means no budget.
- After every call it records the request, the tokens (including prompt-cache hits) and the latency
  in the `ai_usage` table. The AI Lab page shows these numbers.
- Counters live in Redis so the API and the worker share them. Without Redis, each process counts
  for itself.
- Once a limit is hit, calls are refused and the app degrades ([0015](0015-graceful-degradation.md)).

## Consequences

- A call's size is only known after it finishes, so the call that crosses the budget still
  completes. Every call after it is refused until the window resets.
- Spending is visible per model and per day in the AI Lab.

## Where in the code

`backend/app/ai/usage.py`, `models/usage.py`, `api/lab.py`. PLAN.md §23.
