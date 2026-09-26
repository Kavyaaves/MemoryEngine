"""GET /api/search — hybrid search without the agent (used by the Media page and the AI Lab)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.router import get_router
from app.core.ratelimit import rate_limit
from app.core.timeutils import end_of_day, start_of_day
from app.db import get_session
from app.models import User
from app.retrieval.hybrid import MODES, HybridRetriever
from app.retrieval.query import SearchFilters
from app.schemas.api import SearchOut

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchOut)
async def search(q: str = Query(min_length=1, max_length=500), start: date | None = None, end: date | None = None,
                 person_id: uuid.UUID | None = None, source_type: str | None = None,
                 k: int = Query(20, ge=1, le=100), mode: str = "hybrid",
                 user: User = Depends(rate_limit("search", 120)), session: AsyncSession = Depends(get_session)):
    """`start` and `end` are inclusive dates in the user's timezone."""
    if mode not in MODES:
        raise HTTPException(422, f"mode must be one of {sorted(MODES)}")
    people = [person_id] if person_id else []
    filters = SearchFilters(user_id=user.id, start=start_of_day(start), end=end_of_day(end), person_ids=people,
                            source_types=[source_type] if source_type else [])
    result = await HybridRetriever(get_router()).search(session, q, filters, k=k, mode=mode, graph_person_ids=people)
    return SearchOut(results=result.evidence, timings_ms=result.timings_ms)
