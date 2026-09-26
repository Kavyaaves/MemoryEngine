"""Sentiment of memories (the local TamilSense model, see app/sentiment/).

    GET  /api/sentiment/timeline?granularity=month&person_id=   mood per period (Life + People pages)
    GET  /api/sentiment/status                                  model, how many are done (AI Lab)
    POST /api/sentiment/analyze                                 analyse this user's remaining memories now
"""

import asyncio
import importlib.util
import uuid
from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.config import get_settings
from app.core.timeutils import PERIOD_FORMATS, end_of_day, local_period, start_of_day
from app.db import get_session
from app.models import Memory, MemoryParticipant, User
from app.schemas.api import MoodBucket, MoodTimelineOut, SentimentStatusOut
from app.sentiment.pipeline import backfill, count_status

router = APIRouter(prefix="/sentiment", tags=["sentiment"])
LABELS = ("positive", "negative", "neutral")

_running: dict[uuid.UUID, asyncio.Task] = {}  # user id → their "analyse now" run (one at a time per user)


@router.get("/timeline", response_model=MoodTimelineOut)
async def mood_timeline(granularity: str = "month", start: date | None = None, end: date | None = None,
                        person_id: uuid.UUID | None = None,
                        user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if granularity not in PERIOD_FORMATS:
        raise HTTPException(422, "granularity must be year, month or day")
    period = local_period(Memory.timestamp, granularity).label("period")
    label = Memory.meta[("sentiment", "label")].astext.label("label")

    # How many positive / negative / neutral memories in each period.
    query = select(period, label, func.count()).where(
        Memory.user_id == user.id, Memory.timestamp.is_not(None), label.in_(LABELS))
    if start:
        query = query.where(Memory.timestamp >= start_of_day(start))
    if end:
        query = query.where(Memory.timestamp < end_of_day(end))
    if person_id:  # only memories this person wrote or is mentioned in
        query = query.where(Memory.id.in_(select(MemoryParticipant.memory_id)
                                          .where(MemoryParticipant.person_id == person_id)))
    rows = await session.execute(query.group_by(period, label))

    counts: dict[str, Counter] = defaultdict(Counter)
    for bucket, sentiment, count in rows.all():
        counts[bucket][sentiment] += count
    buckets = []
    for bucket, c in sorted(counts.items()):
        total = c["positive"] + c["negative"] + c["neutral"]
        buckets.append(MoodBucket(period=bucket, positive=c["positive"], negative=c["negative"], neutral=c["neutral"],
                                  mood=round((c["positive"] - c["negative"]) / total, 3) if total else 0.0))
    return MoodTimelineOut(buckets=buckets)


async def _status(user: User) -> SentimentStatusOut:
    settings = get_settings()
    counts = await count_status(user.id)
    task = _running.get(user.id)
    return SentimentStatusOut(enabled=settings.sentiment_enabled,
                              installed=importlib.util.find_spec("transformers") is not None,
                              model=settings.sentiment_model, done=counts["done"], remaining=counts["remaining"],
                              running=task is not None and not task.done())


@router.get("/status", response_model=SentimentStatusOut)
async def sentiment_status(user: User = Depends(current_user)):
    return await _status(user)


@router.post("/analyze", response_model=SentimentStatusOut, status_code=202)
async def analyze_now(user: User = Depends(current_user)):
    """Starts analysing in the background and returns at once; poll /status to follow it."""
    if not get_settings().sentiment_enabled:
        raise HTTPException(409, "sentiment is switched off (SENTIMENT_ENABLED=false)")
    task = _running.get(user.id)
    if task is None or task.done():
        _running[user.id] = asyncio.create_task(backfill(user_id=user.id))
    return await _status(user)
