"""The shared Redis client — optional.

Redis holds the job queue (workers/queue.py) and counters shared by every process: rate limits
(core/ratelimit.py) and the AI request and token limits (ai/usage.py). The app works without it:

- REDIS_URL empty: no Redis at all. Uploads are processed inside the API process, and limits
  are counted in each process separately.
- REDIS_URL set, but Redis unreachable: after one failed call, Redis is skipped for
  RETRY_AFTER_SECONDS and then tried again. Without this, every call would wait for its own
  connection timeout — about 2 seconds each, several times per AI call.

Callers ask `redis_usable()` first and call `mark_unreachable(error)` when a Redis call fails.
"""

import logging
import time

import redis.asyncio as aioredis

from app.config import get_settings

log = logging.getLogger(__name__)
CONNECT_TIMEOUT_SECONDS = 2
READ_TIMEOUT_SECONDS = 5
RETRY_AFTER_SECONDS = 30

_redis: aioredis.Redis | None = None
_skip_until = 0.0  # time.monotonic() value until which Redis is not tried


def get_redis() -> aioredis.Redis | None:
    """The lazily-connected client, or None when REDIS_URL is empty."""
    global _redis
    url = get_settings().redis_url
    if not url:
        return None
    if _redis is None:
        _redis = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
                                   socket_timeout=READ_TIMEOUT_SECONDS)
    return _redis


def redis_usable() -> bool:
    """False when Redis isn't configured, or failed less than RETRY_AFTER_SECONDS ago."""
    return bool(get_settings().redis_url) and time.monotonic() >= _skip_until


def mark_unreachable(error: Exception) -> None:
    """Skip Redis for RETRY_AFTER_SECONDS. Logs once per outage, not once per call."""
    global _skip_until
    if time.monotonic() >= _skip_until:
        log.warning("Redis unreachable (%s: %s); continuing without it, retrying in %d s",
                    type(error).__name__, error, RETRY_AFTER_SECONDS)
    _skip_until = time.monotonic() + RETRY_AFTER_SECONDS


async def redis_ok() -> bool:
    if not redis_usable():
        return False
    try:
        return bool(await get_redis().ping())
    except Exception as exc:
        mark_unreachable(exc)
        return False
