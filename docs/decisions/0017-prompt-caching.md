# 0017. Order prompts fixed-first so OpenAI can cache them

- **Status:** Accepted

## Context

OpenAI automatically caches the start of a prompt when it is at least 1,024 tokens long and exactly
the same as a recent one. Cached input tokens are cheaper and faster. But any change near the start,
such as today's date in the system prompt, breaks the cache for everything after it.

## Decision

- Prompts are ordered fixed-first: system prompt → earlier turns → evidence and question.
- System prompts never contain anything that changes (dates and questions go in the user message).
- The answer prompt's fixed part is kept above 1,024 tokens. A test checks it stays that long.
- Each request carries a `prompt_cache_key`, and the cached token count of every call is saved in
  `ai_usage.cached_input_tokens` (migration `0002`).

## Consequences

- Repeat questions are cheaper and start answering sooner.
- `python -m app.evaluation.cache_benchmark` measures the effect on latency.
- Editing a system prompt needs care: keep it fixed and long enough, or the test fails.

## Where in the code

`backend/app/ai/prompts/`, `ai/providers/openai.py`, `tests/test_prompts.py`,
`alembic/versions/0002_cached_input_tokens.py`, `evaluation/cache_benchmark.py`.
