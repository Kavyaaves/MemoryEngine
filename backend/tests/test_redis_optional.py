"""The app without Redis: no REDIS_URL, or a Redis that stops answering (see core/redis.py)."""

import time

import pytest

import app.core.redis as redis_module
from app.ai.providers.base import TokenUsage
from app.ai.usage import UsageManager
from app.config import Settings


class DeadRedis:
    """A Redis client whose every call fails, counting how often it was tried."""

    def __init__(self):
        self.calls = 0

    async def _fail(self, *args, **kwargs):
        self.calls += 1
        raise ConnectionError("connection refused")

    get = incrby = expire = incr = ping = _fail


@pytest.fixture
def fresh_redis_state(monkeypatch):
    """Each test starts with Redis 'up' and REDIS_URL set, whatever an earlier test did."""
    monkeypatch.setattr(redis_module, "_skip_until", 0.0)
    monkeypatch.setattr(redis_module, "_redis", None)
    monkeypatch.setattr(redis_module, "get_settings", lambda: Settings(redis_url="redis://localhost:6379/0"))


async def test_after_one_failure_redis_is_skipped_instead_of_timing_out_on_every_call(fresh_redis_state, monkeypatch):
    dead = DeadRedis()
    usage = UsageManager(Settings(max_tokens_per_window=100), redis=dead, persist=False)

    await usage.check("openai")  # the first Redis call fails...
    assert dead.calls == 1
    for _ in range(5):  # ...then nothing touches Redis: no more waiting
        await usage.check("openai")
        await usage.record(provider="openai", model="m", task="fast", tokens=TokenUsage(10, 5))
    assert dead.calls == 1
    assert (await usage.token_window_status())["tokens_used_in_window"] == 75  # counted in-process meanwhile

    now = time.monotonic()
    monkeypatch.setattr(redis_module.time, "monotonic", lambda: now + redis_module.RETRY_AFTER_SECONDS + 1)
    await usage.check("openai")
    assert dead.calls == 2  # tried again once the pause is over


async def test_empty_redis_url_means_no_redis_at_all(monkeypatch):
    monkeypatch.setattr(redis_module, "_redis", None)
    monkeypatch.setattr(redis_module, "get_settings", lambda: Settings(redis_url=""))
    assert redis_module.get_redis() is None
    assert redis_module.redis_usable() is False
    assert await redis_module.redis_ok() is False


async def test_health_check_marks_redis_down_once(fresh_redis_state, monkeypatch):
    dead = DeadRedis()
    monkeypatch.setattr(redis_module, "_redis", dead)
    assert await redis_module.redis_ok() is False
    assert await redis_module.redis_ok() is False
    assert dead.calls == 1
