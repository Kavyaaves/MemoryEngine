"""The FastAPI application. Run with:  uvicorn app.main:app --reload

Reading order for the backend:
    main.py → api/ (routes) → ingestion/ (uploads) → retrieval/ (search) → agents/ (ask) → ai/ (models)
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api import api_router
from app.config import Settings, get_settings
from app.observability.tracing import setup_tracing

log = logging.getLogger(__name__)
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}


def _configure_langsmith(settings: Settings) -> None:
    """LangChain reads LangSmith settings from environment variables, but values in a .env
    file only reach our Settings object — so copy them into the environment."""
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_TRACING", "true" if settings.langsmith_tracing else "false")
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.environment == "production" and settings.secret_key == "change-me-in-production":
        raise RuntimeError("SECRET_KEY must be set in production")
    _configure_langsmith(settings)

    app = FastAPI(title="Personal Memory Engine", version="0.1.0",
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(ConnectionError)
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def database_unavailable(request: Request, exc: Exception):
        """Database (or another backing service) unreachable → a clear 503 instead of a bare 500."""
        log.error("service unavailable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Please try again shortly."})

    app.include_router(api_router)
    setup_tracing(settings, app)
    return app


app = create_app()
