"""The AI Lab page (PLAN §44): what the AI layer is doing and how it is configured.

    GET /api/lab/usage    requests / tokens / errors / latency per provider, model, task and day,
                          plus the limits and how much of the current token budget is used
    GET /api/lab/config   providers, routing, models and retrieval settings
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import PROMPT_VERSION
from app.ai.providers.router import get_router
from app.auth.security import current_user
from app.config import get_settings
from app.db import get_session
from app.models import AIUsage, User

router = APIRouter(prefix="/lab", tags=["lab"])


@router.get("/usage")
async def usage(days: int = Query(30, ge=1, le=365), user: User = Depends(current_user),
                session: AsyncSession = Depends(get_session)):
    failures = func.sum(cast(~AIUsage.success, Integer))  # count rows where success is false
    rows = await session.execute(
        select(AIUsage.provider, AIUsage.model, AIUsage.task, AIUsage.day, func.count(),
               func.sum(AIUsage.input_tokens), func.sum(AIUsage.output_tokens), func.sum(AIUsage.cached_input_tokens),
               failures, func.avg(AIUsage.latency_ms))
        # the user's own calls, plus background calls (e.g. embedding backfill) that have no user
        .where(AIUsage.day >= date.today() - timedelta(days=days),
               or_(AIUsage.user_id == user.id, AIUsage.user_id.is_(None)))
        .group_by(AIUsage.provider, AIUsage.model, AIUsage.task, AIUsage.day)
        .order_by(AIUsage.day.desc()))
    settings = get_settings()
    return {
        "providers": [
            {"provider": provider, "model": model, "task": task, "day": day.isoformat(), "request_count": count,
             "input_tokens": int(tokens_in or 0), "output_tokens": int(tokens_out or 0),
             "cached_input_tokens": int(tokens_cached or 0), "errors": int(errors or 0),
             "avg_latency_ms": round(float(latency or 0))}
            for provider, model, task, day, count, tokens_in, tokens_out, tokens_cached, errors, latency in rows.all()],
        "limits": {"max_daily_requests": settings.max_daily_requests,
                   "max_monthly_requests": settings.max_monthly_requests,
                   **await get_router().usage.token_window_status()},
    }


@router.get("/config")
async def config(user: User = Depends(current_user)):
    settings = get_settings()
    ai_router = get_router()
    return {
        "providers": [{"name": name, "configured": p.configured} for name, p in ai_router.providers.items()],
        "routing": ai_router.routing,
        "embedding_provider": "openai",
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "reranker": settings.reranker,
        "mmr_lambda": settings.mmr_lambda,
        "top_k": settings.retrieval_top_k,
        "prompt_version": PROMPT_VERSION,
        # OpenAI's model for each task.
        "models": {"reasoning": settings.openai_reasoning_model, "fast": settings.openai_fast_model,
                   "speech": settings.openai_speech_model},
    }
