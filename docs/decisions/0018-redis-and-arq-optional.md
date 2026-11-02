# 0018. Background jobs with Redis + arq, and Redis is optional

- **Status:** Accepted

## Context

Importing a large chat takes minutes: parse, hash, normalise, resolve people, build the graph, embed,
analyse sentiment, update the universe. That can't run inside an HTTP request. A queue also needs
somewhere to keep counters shared by every process (rate limits, AI quotas).

## Decision

- Uploads create a job and put it on a **Redis** queue. A separate **arq** worker process runs it.
- arq was chosen because it is small and async-native, so the worker shares the app's async code
  (SQLAlchemy async sessions, async OpenAI calls).
- The same Redis holds rate-limit counters and AI usage counters.
- **Redis is optional**:
  - `REDIS_URL` empty, or `INLINE_INGESTION=true`: jobs run inside the API process, and limits are
    counted per process.
  - Redis set but unreachable: after one failed call it is skipped for a while, instead of every
    call waiting about 2 seconds for its own timeout.
- The worker also runs scheduled catch-up jobs (arq `cron`): embeddings at :00 and :30, sentiment
  at :15 and :45, and the Memory Universe at :20 and :50. Each one only handles what an import
  missed, for example while OpenAI was unavailable.
- Up to 4 jobs run at once, each with a one-hour timeout for very large exports.

## Consequences

- Local development needs no Redis and no worker.
- In production the API stays responsive during big imports, and the worker can be restarted on its own.

## Where in the code

`backend/app/workers/queue.py`, `workers/worker.py`, `core/redis.py`, `core/ratelimit.py`. PLAN.md §24.
