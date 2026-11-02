"""The AI router: picks a provider for each task, retries, and logs usage.

Every task currently goes to OpenAI (DEFAULT_ROUTING). The router still takes a list of
providers per task, so a fallback provider can be added later without changing callers.

For each provider: skip it if unconfigured or over quota; otherwise try (once more on a
transient error). If every provider fails, AIUnavailable is raised — callers catch it and
degrade gracefully (keyword-only search, extractive answers) instead of erroring.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from app.ai.providers.base import (
    AIProvider,
    AIUnavailable,
    Generation,
    Message,
    ProviderError,
    QuotaExceeded,
    T,
    Task,
    TokenUsage,
    Transcript,
)
from app.ai.usage import UsageManager
from app.observability.tracing import tracer

log = logging.getLogger(__name__)

DEFAULT_ROUTING: dict[str, list[str]] = {
    task: ["openai"] for task in ("reasoning", "extraction", "fast", "rewrite", "embedding", "speech",
                                  "teacher", "derived")
}
ATTEMPTS_PER_PROVIDER = 2

# A provider call returns (result, token usage or None).
ProviderCall = Callable[[AIProvider], Awaitable[tuple[object, TokenUsage | None]]]


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class AIRouter:
    def __init__(self, providers: Sequence[AIProvider], usage: UsageManager,
                 routing: dict[str, list[str]] | None = None, retry_delay_seconds: float = 1.5):
        self.providers = {p.name: p for p in providers}
        self.usage = usage
        self.routing = routing or DEFAULT_ROUTING
        # Pause before retrying a transient error ("high demand", timeouts): an instant retry usually fails too.
        self.retry_delay_seconds = retry_delay_seconds

    def chain(self, task: Task) -> list[AIProvider]:
        """Configured providers for a task, in preference order."""
        names = self.routing.get(task, [])
        return [self.providers[n] for n in names if n in self.providers and self.providers[n].configured]

    def available(self, task: Task) -> bool:
        return bool(self.chain(task))

    async def _call_with_fallback(self, task: Task, call: ProviderCall, user_id: uuid.UUID | None):
        errors: list[str] = []
        for provider in self.chain(task):
            model = provider.model_for(task)
            try:
                await self.usage.check(provider.name)
            except QuotaExceeded as exc:
                errors.append(str(exc))
                continue  # over quota → next provider

            for attempt in range(1, ATTEMPTS_PER_PROVIDER + 1):
                start = time.perf_counter()
                try:
                    with tracer.start_as_current_span(f"ai.{task}", attributes={"ai.provider": provider.name,
                                                                                 "ai.model": model}):
                        result, tokens = await call(provider)
                except ProviderError as exc:
                    await self.usage.record(provider=provider.name, model=model, task=task, success=False,
                                            error=str(exc), latency_ms=_elapsed_ms(start), user_id=user_id)
                    errors.append(f"{provider.name}: {exc}")
                    log.warning("%s failed for %s (attempt %d): %s", provider.name, task, attempt, exc)
                    if not exc.retryable:
                        break  # e.g. bad API key, retired model or quota → retrying won't help
                    if attempt < ATTEMPTS_PER_PROVIDER:
                        await asyncio.sleep(self.retry_delay_seconds)
                    continue
                await self.usage.record(provider=provider.name, model=model, task=task, latency_ms=_elapsed_ms(start),
                                        tokens=tokens or TokenUsage(), user_id=user_id)
                return result
        raise AIUnavailable("; ".join(errors) or f"no provider configured for task '{task}'")

    # ---- one method per kind of request ------------------------------------------------

    async def generate(self, task: Task, messages: Sequence[Message], *, temperature: float = 0.2,
                       max_tokens: int | None = None, user_id=None) -> Generation:
        async def call(provider):
            generation = await provider.generate(task, messages, temperature=temperature, max_tokens=max_tokens)
            return generation, generation.usage

        return await self._call_with_fallback(task, call, user_id)

    async def structured(self, task: Task, schema: type[T], messages: Sequence[Message], *, user_id=None) -> T:
        async def call(provider):
            return await provider.structured(task, schema, messages)

        return await self._call_with_fallback(task, call, user_id)

    async def embed(self, texts: Sequence[str], *, task_type: str = "RETRIEVAL_DOCUMENT",
                    user_id=None) -> list[list[float]]:
        async def call(provider):
            return await provider.embed(texts, task_type=task_type), None

        return await self._call_with_fallback("embedding", call, user_id)

    async def transcribe(self, audio: bytes, filename: str, *, user_id=None) -> Transcript:
        async def call(provider):
            return await provider.transcribe(audio, filename), None

        return await self._call_with_fallback("speech", call, user_id)

    async def stream(self, task: Task, messages: Sequence[Message], *, temperature: float = 0.2,
                     user_id=None, on_provider: Callable[[str, str], None] | None = None) -> AsyncIterator[str]:
        """Yield answer text as it is generated.

        Falling back is only possible before the first chunk: once text has reached the user
        we can't switch models mid-sentence, so a later failure raises ProviderError.
        `on_provider(name, model)` is called when the first chunk arrives.
        """
        errors: list[str] = []
        for provider in self.chain(task):
            try:
                await self.usage.check(provider.name)
            except QuotaExceeded as exc:
                errors.append(str(exc))
                continue
            model = provider.model_for(task)
            start = time.perf_counter()
            characters_sent = 0
            reported: list[TokenUsage] = []  # the provider reports token usage when the stream ends
            try:
                async for chunk in provider.stream(task, messages, temperature=temperature, on_usage=reported.append):
                    if characters_sent == 0 and on_provider:
                        on_provider(provider.name, model)
                    characters_sent += len(chunk)
                    yield chunk
            except ProviderError as exc:
                await self.usage.record(provider=provider.name, model=model, task=task, success=False,
                                        error=str(exc), latency_ms=_elapsed_ms(start), user_id=user_id)
                if characters_sent:
                    raise
                errors.append(f"{provider.name}: {exc}")
                continue
            # If the provider reported no usage, estimate the output at ~4 characters per token.
            tokens = reported[-1] if reported else TokenUsage(output_tokens=characters_sent // 4)
            await self.usage.record(provider=provider.name, model=model, task=task, tokens=tokens,
                                    latency_ms=_elapsed_ms(start), user_id=user_id)
            return
        raise AIUnavailable("; ".join(errors) or f"no provider configured for task '{task}'")


_router: AIRouter | None = None


def get_router() -> AIRouter:
    """The app-wide router (created on first use)."""
    global _router
    if _router is None:
        from app.ai.providers.openai import OpenAIProvider
        from app.config import get_settings
        from app.core.redis import get_redis

        settings = get_settings()
        _router = AIRouter([OpenAIProvider(settings)], UsageManager(settings, redis=get_redis()))
    return _router
