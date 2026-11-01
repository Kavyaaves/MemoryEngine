"""HTTP routes, one module per resource. Everything is mounted under /api (see docs/api-contract.md).

Routes stay thin: they check input and ownership, then call into ingestion/, retrieval/,
agents/ or people/ where the real work happens.
"""

from fastapi import APIRouter

from app.api import (
    ask,
    auth,
    health,
    lab,
    media,
    people,
    photos,
    search,
    sentiment,
    sources,
    timeline,
    universe,
    uploads,
)

api_router = APIRouter(prefix="/api")
for module in (auth, uploads, sources, search, ask, timeline, universe, people, lab, media, photos, sentiment, health):
    api_router.include_router(module.router)
