import time

import pytest

from app.ai.providers.base import (
    AIUnavailable,
    Generation,
    ProviderError,
    QuotaExceeded,
    TokenUsage,
    classify_exception,
)
from app.ai.providers.router import AIRouter
from app.ai.usage import UsageManager
from app.config import Settings


class FakeProvider:
    def __init__(self, name, *, fail=None, configured=True, chunks=("hel", "lo")):
        self.name = name
        self.fail = fail
        self._configured = configured
        self.calls = 0
        self.chunks = chunks

    @property
    def configured(self):
        return self._configured

    def model_for(self, task):
        return f"{self.name}-model"

    async def generate(self, task, messages, **kw):
        self.calls += 1
        if self.fail:
            raise self.fail
        return Generation(text=f"from {self.name}", provider=self.name, model="m", usage=TokenUsage(3, 4))

    async def stream(self, task, messages, **kw):
        self.calls += 1
        if self.fail:
            raise self.fail
        for c in self.chunks:
            yield c


class RecordingUsage(UsageManager):
    """A usage manager that remembers what the router logged (no database)."""

    def __init__(self, settings):
        super().__init__(settings, redis=None, persist=False)
        self.rows = []

    async def record(self, **row):
        self.rows.append(row)
        await super().record(**row)


# The app routes every task to OpenAI only. These tests give the router a second provider
# ("backup") to check that its retry and fallback logic still works.
TWO_PROVIDERS = {"reasoning": ["primary", "backup"]}


def make_router(*providers, daily=100, routing=None):
    s = Settings(max_daily_requests=daily, max_monthly_requests=1000)
    return AIRouter(providers, RecordingUsage(s), routing=routing or TWO_PROVIDERS, retry_delay_seconds=0)


async def test_first_provider_in_the_chain_is_used():
    r = make_router(FakeProvider("primary"), FakeProvider("backup"))
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from primary"


async def test_falls_back_when_the_first_provider_is_over_quota():
    primary = FakeProvider("primary", fail=QuotaExceeded("429 rate limit"))
    r = make_router(primary, FakeProvider("backup"))
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from backup"
    assert primary.calls == 1  # quota errors are not retried


async def test_retries_transient_error_once_then_falls_back():
    primary = FakeProvider("primary", fail=ProviderError("503 unavailable", retryable=True))
    r = make_router(primary, FakeProvider("backup"))
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from backup"
    assert primary.calls == 2


async def test_unconfigured_providers_are_skipped_and_all_failing_raises():
    r = make_router(FakeProvider("primary", configured=False),
                    FakeProvider("backup", fail=ProviderError("bad key", retryable=False)))
    with pytest.raises(AIUnavailable):
        await r.generate("reasoning", [("user", "hi")])
    assert not make_router(FakeProvider("primary", configured=False)).available("embedding")


async def test_local_quota_guard_blocks_after_limit():
    primary, backup = FakeProvider("primary"), FakeProvider("backup")
    r = make_router(primary, backup, daily=2)
    for _ in range(2):
        await r.generate("reasoning", [("user", "hi")])
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from backup"
    assert primary.calls == 2


async def test_stream_falls_back_before_first_token():
    r = make_router(FakeProvider("primary", fail=ProviderError("boom")), FakeProvider("backup", chunks=("a", "b")))
    seen = []
    out = [c async for c in r.stream("reasoning", [("user", "x")], on_provider=lambda p, m: seen.append(p))]
    assert out == ["a", "b"] and seen == ["backup"]


async def test_every_task_goes_to_openai():
    r = AIRouter([FakeProvider("openai")], UsageManager(Settings(), persist=False))
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from openai"
    for task in ("reasoning", "fast", "rewrite", "extraction", "vision", "embedding", "speech"):
        assert [p.name for p in r.chain(task)] == ["openai"]


async def test_token_budget_refuses_calls_once_used_up_until_the_window_resets(monkeypatch):
    settings = Settings(max_tokens_per_window=10, token_window_hours=1)
    primary = FakeProvider("primary")  # each call uses 3 + 4 = 7 tokens
    r = AIRouter([primary], UsageManager(settings, persist=False), routing={"reasoning": ["primary"]},
                 retry_delay_seconds=0)
    await r.generate("reasoning", [("user", "hi")])  # 7 used: under budget
    await r.generate("reasoning", [("user", "hi")])  # 14 used: crosses the budget, but was allowed to start
    with pytest.raises(AIUnavailable, match="token budget"):
        await r.generate("reasoning", [("user", "hi")])
    assert primary.calls == 2
    status = await r.usage.token_window_status()
    assert status["tokens_used_in_window"] == 14 and status["max_tokens_per_window"] == 10

    # An hour later a new window starts with a fresh budget.
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 3600)
    assert (await r.generate("reasoning", [("user", "hi")])).text == "from primary"


async def test_no_token_budget_when_set_to_zero():
    r = AIRouter([FakeProvider("primary")], UsageManager(Settings(max_tokens_per_window=0), persist=False),
                 routing={"reasoning": ["primary"]})
    for _ in range(5):
        await r.generate("reasoning", [("user", "hi")])


class StreamWithUsage(FakeProvider):
    async def stream(self, task, messages, *, on_usage=None, **kw):
        yield "hello"
        on_usage(TokenUsage(input_tokens=1500, output_tokens=2, cached_input_tokens=1280))


async def test_streamed_usage_reported_by_the_provider_is_logged_including_cached_tokens():
    r = make_router(StreamWithUsage("primary"))
    assert [c async for c in r.stream("reasoning", [("user", "x")])] == ["hello"]
    assert r.usage.rows[-1]["tokens"] == TokenUsage(1500, 2, 1280)

    r = make_router(FakeProvider("primary", chunks=("12345678",)))  # reports nothing → estimated
    assert [c async for c in r.stream("reasoning", [("user", "x")])] == ["12345678"]
    assert r.usage.rows[-1]["tokens"] == TokenUsage(output_tokens=2)


def test_exception_classification():
    assert isinstance(classify_exception(Exception("429 Too Many Requests")), QuotaExceeded)
    assert classify_exception(Exception("401 invalid api key")).retryable is False
    assert classify_exception(Exception("connection reset")).retryable is True
