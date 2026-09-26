"""The timeline behind the 3D Life page (PLAN §28).

    GET /api/timeline?granularity=month   → how many memories per month, by source and top people
    GET /api/timeline/day/2024-06-14      → every memory on one day
"""

from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import current_user
from app.core.timeutils import PERIOD_FORMATS, end_of_day, local_period, start_of_day
from app.db import get_session
from app.models import Memory, Person, User
from app.retrieval.evidence import build_evidence
from app.schemas.api import DayOut, TimelineBucket, TimelineOut

router = APIRouter(prefix="/timeline", tags=["timeline"])
MAX_MEMORIES_PER_DAY = 500


def _within(query, user: User, start: date | None, end: date | None):
    """Only this user's dated memories between `start` and `end` (inclusive dates)."""
    query = query.where(Memory.user_id == user.id, Memory.timestamp.is_not(None))
    if start:
        query = query.where(Memory.timestamp >= start_of_day(start))
    if end:
        query = query.where(Memory.timestamp < end_of_day(end))
    return query


@router.get("", response_model=TimelineOut)
async def timeline(granularity: str = "month", start: date | None = None, end: date | None = None,
                   user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if granularity not in PERIOD_FORMATS:
        raise HTTPException(422, "granularity must be year, month or day")
    period = local_period(Memory.timestamp, granularity).label("period")

    by_source = _within(select(period, Memory.source_type, func.count()), user, start, end)
    by_source = await session.execute(by_source.group_by(period, Memory.source_type))
    sources_per_period: dict[str, Counter] = defaultdict(Counter)
    for bucket, source_type, count in by_source.all():
        sources_per_period[bucket][source_type] += count

    by_person = select(period, Person.display_name, func.count()).join(Person, Person.id == Memory.author_person_id)
    by_person = _within(by_person.where(Person.is_self.is_(False)), user, start, end)
    by_person = await session.execute(by_person.group_by(period, Person.display_name))
    people_per_period: dict[str, Counter] = defaultdict(Counter)
    for bucket, name, count in by_person.all():
        people_per_period[bucket][name] += count

    buckets = [TimelineBucket(period=bucket, count=sum(sources.values()), sources=dict(sources),
                              top_people=[name for name, _ in people_per_period[bucket].most_common(5)])
               for bucket, sources in sorted(sources_per_period.items())]
    return TimelineOut(buckets=buckets)


@router.get("/day/{day}", response_model=DayOut)
async def day(day: date, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    query = _within(select(Memory.id), user, day, day).order_by(Memory.timestamp).limit(MAX_MEMORIES_PER_DAY)
    memory_ids = (await session.execute(query)).scalars().all()
    ranked = [(memory_id, 1.0, ["temporal"]) for memory_id in memory_ids]
    return DayOut(date=day.isoformat(), memories=await build_evidence(session, user.id, ranked, []))
