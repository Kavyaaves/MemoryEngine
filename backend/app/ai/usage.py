"""AI usage manager / quota guard (PLAN §23).

- check(provider): raises QuotaExceeded when a limit is hit:
    * requests: today's or this month's request limit (per provider)
    * tokens:   the token budget for the current time window (MAX_TOKENS_PER_WINDOW tokens every
                TOKEN_WINDOW_HOURS hours, all providers together)
- record(...):     counts the request and its tokens, and saves a row to `ai_usage` (for the AI Lab page).

The token budget is checked *before* a call, but a call's size is only known *after* it, so the
call that crosses the budget still finishes; every call after it is refused until the window
resets. Refused calls make the app degrade gracefully (keyword-only search, answers that list
the evidence) — exactly as when OpenAI itself rate-limits us.

Counters live in Redis so the API and the worker share them. Without Redis (REDIS_URL empty, or
Redis unreachable — see core/redis.py), an in-process counter is used instead: limits still
apply, just per process.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from app.ai.providers.base import QuotaExceeded, TokenUsage
from app.config import Settings
from app.core.redis import mark_unreachable, redis_usable
from app.db import SessionLocal
from app.models import AIUsage

log = logging.getLogger(__name__)
TWO_DAYS = 60 * 60 * 48
FORTY_DAYS = 60 * 60 * 24 * 40
SECONDS_PER_HOUR = 60 * 60


class UsageManager:
    def __init__(self, settings: Settings, redis=None, persist: bool = True):
        self.settings = settings
        self.redis = redis
        self.persist = persist  # False in tests: no database writes
        self._local_counts: dict[str, int] = {}
        self._background_tasks: set[asyncio.Task] = set()  # keep references so tasks aren't garbage-collected

    @staticmethod
    def _counter_keys(provider: str) -> tuple[str, str]:
        now = datetime.now(UTC)
        return f"ai:req:{provider}:{now:%Y-%m-%d}", f"ai:req:{provider}:{now:%Y-%m}"

    def _token_window(self) -> tuple[str, datetime]:
        """The Redis key for the current token window, and when that window ends.

        Windows are fixed blocks of TOKEN_WINDOW_HOURS counted from 1 Jan 1970 UTC, so a
        24-hour window always resets at midnight UTC.
        """
        window_seconds = self.settings.token_window_hours * SECONDS_PER_HOUR
        window_number = int(time.time() // window_seconds)
        resets_at = datetime.fromtimestamp((window_number + 1) * window_seconds, UTC)
        return f"ai:tok:{self.settings.token_window_hours}h:{window_number}", resets_at

    def _use_redis(self) -> bool:
        return self.redis is not None and redis_usable()

    async def _read(self, key: str) -> int:
        if self._use_redis():
            try:
                return int(await self.redis.get(key) or 0)
            except Exception as exc:
                mark_unreachable(exc)  # the next calls skip Redis instead of each waiting for a timeout
        return self._local_counts.get(key, 0)

    async def _increment(self, key: str, expire_seconds: int, amount: int = 1) -> None:
        self._local_counts[key] = self._local_counts.get(key, 0) + amount
        if self._use_redis():
            try:
                await self.redis.incrby(key, amount)
                await self.redis.expire(key, expire_seconds)
            except Exception as exc:
                mark_unreachable(exc)

    async def token_window_status(self) -> dict:
        """How much of the current token budget is used — for the AI Lab page."""
        key, resets_at = self._token_window()
        return {"max_tokens_per_window": self.settings.max_tokens_per_window,
                "token_window_hours": self.settings.token_window_hours,
                "tokens_used_in_window": await self._read(key),
                "token_window_resets_at": resets_at.isoformat()}

    async def check(self, provider: str) -> None:
        day_key, month_key = self._counter_keys(provider)
        if await self._read(day_key) >= self.settings.max_daily_requests:
            raise QuotaExceeded(f"{provider}: daily request limit ({self.settings.max_daily_requests}) reached")
        if await self._read(month_key) >= self.settings.max_monthly_requests:
            raise QuotaExceeded(f"{provider}: monthly request limit ({self.settings.max_monthly_requests}) reached")

        budget = self.settings.max_tokens_per_window
        if budget:  # 0 = no token budget
            key, resets_at = self._token_window()
            if await self._read(key) >= budget:
                raise QuotaExceeded(f"token budget ({budget:,} tokens per {self.settings.token_window_hours} h) "
                                    f"used up; it resets at {resets_at:%Y-%m-%d %H:%M} UTC")

    async def record(self, *, provider: str, model: str, task: str, tokens: TokenUsage | None = None,
                     latency_ms: int = 0, success: bool = True, error: str | None = None,
                     user_id: uuid.UUID | None = None) -> None:
        tokens = tokens or TokenUsage()
        day_key, month_key = self._counter_keys(provider)
        await self._increment(day_key, TWO_DAYS)
        await self._increment(month_key, FORTY_DAYS)
        # Every token counts towards the budget, including ones served from the prompt cache.
        # (Embedding calls report no token counts here, so bulk imports don't use up the budget.)
        spent = tokens.input_tokens + tokens.output_tokens
        if spent:
            token_key, _ = self._token_window()
            await self._increment(token_key, 2 * self.settings.token_window_hours * SECONDS_PER_HOUR, amount=spent)
        if not self.persist:
            return

        row = AIUsage(provider=provider, model=model, task=task, day=datetime.now(UTC).date(),
                      input_tokens=tokens.input_tokens, output_tokens=tokens.output_tokens,
                      cached_input_tokens=tokens.cached_input_tokens, latency_ms=latency_ms,
                      success=success, error=error[:2000] if error else None, user_id=user_id)
        # Save in the background so logging never slows down (or breaks) the actual request.
        task_handle = asyncio.create_task(self._save(row))
        self._background_tasks.add(task_handle)
        task_handle.add_done_callback(self._background_tasks.discard)

    @staticmethod
    async def _save(row) -> None:
        try:
            async with SessionLocal() as session:
                session.add(row)
                await session.commit()
        except Exception as exc:
            log.warning("failed to save AI usage row: %s", exc)
