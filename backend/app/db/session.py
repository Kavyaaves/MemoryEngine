"""Database connection.

- `Base`: every table class in app/models inherits from it.
- `SessionLocal()`: opens a session (a unit of work) — used by background jobs.
- `get_session`: the FastAPI dependency that gives each request its own session.

The engine connects lazily: importing this module never touches the database.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
# pool_pre_ping: check a pooled connection is still alive before using it (hosted
# databases close idle connections).
engine = create_async_engine(_settings.database_url, pool_pre_ping=True,
                             pool_size=_settings.db_pool_size, max_overflow=_settings.db_max_overflow)
# expire_on_commit=False: objects stay readable after commit (handy for returning them from routes).
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
