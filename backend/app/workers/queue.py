"""Handing ingestion jobs to the background worker (PLAN §24).

    upload API → enqueue_ingestion(job_id) → Redis queue → worker.py → pipeline.process_job

Without Redis — REDIS_URL empty, Redis unreachable, or INLINE_INGESTION=true — the job runs
inside the API process instead, so development works without a worker.
"""

import asyncio
import logging
import uuid

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.redis import mark_unreachable, redis_usable
from app.ingestion.pipeline import build_universe, process_job

log = logging.getLogger(__name__)
_queue: ArqRedis | None = None
_inline_jobs: set[asyncio.Task] = set()  # keep references so running tasks aren't garbage-collected


LOCAL_REDIS = "redis://localhost:6379/0"


def redis_settings() -> RedisSettings:
    """Connection settings for arq. The worker always needs Redis: with REDIS_URL empty it tries
    a local one, and arq reports the connection error when there is none."""
    return RedisSettings.from_dsn(get_settings().redis_url or LOCAL_REDIS)


async def enqueue_ingestion(job_id: uuid.UUID) -> str:
    """Returns "queued" (the worker will run it) or "inline" (running in this process)."""
    global _queue
    if not get_settings().inline_ingestion and redis_usable():
        try:
            if _queue is None:
                settings = redis_settings()
                settings.conn_retries = 0  # fail fast and run the job here, instead of retrying for seconds
                _queue = await create_pool(settings)
            # No fixed arq job id: arq remembers finished ids for an hour and would silently
            # ignore a retry of the same job.
            await _queue.enqueue_job("ingest", str(job_id))
            return "queued"
        except Exception as exc:
            mark_unreachable(exc)
            log.warning("Redis queue unavailable (%s); running ingestion in-process", exc)

    _run_inline(process_job(job_id))
    return "inline"


def _run_inline(coroutine) -> None:
    task = asyncio.create_task(coroutine)
    _inline_jobs.add(task)
    task.add_done_callback(_inline_jobs.discard)


async def enqueue_universe_update(user_id: uuid.UUID) -> str:
    """Place a user's unplaced memories in the Memory Universe in the background (the Memories
    page's "Build my universe" button). Returns "queued" or "inline", like enqueue_ingestion."""
    global _queue
    if not get_settings().inline_ingestion and redis_usable():
        try:
            if _queue is None:
                settings = redis_settings()
                settings.conn_retries = 0
                _queue = await create_pool(settings)
            await _queue.enqueue_job("build_universe", str(user_id))
            return "queued"
        except Exception as exc:
            mark_unreachable(exc)
            log.warning("Redis queue unavailable (%s); building the universe in-process", exc)
    _run_inline(build_universe(user_id))
    return "inline"
