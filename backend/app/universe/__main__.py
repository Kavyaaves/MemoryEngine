"""Command line: build or catch up the Memory Universe for every user.

    python -m app.universe            place unplaced memories, then write AI titles
    python -m app.universe titles     only write AI titles (up to 40 per run)
"""

import asyncio
import logging
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.universe.titles import name_books
from app.universe.updater import update_universe


async def build_all() -> None:
    async with SessionLocal() as session:
        user_ids = list((await session.execute(select(User.id))).scalars())
    for user_id in user_ids:
        async with SessionLocal() as session:
            stats = await update_universe(session, user_id)
        print(f"user {user_id}: {stats.as_dict()}")


async def titles_all() -> None:
    named = await name_books()
    print(f"{named} books named with AI")


async def main(command: str) -> None:
    if command in ("build", ""):
        await build_all()
    await titles_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg not in ("", "build", "titles"):
        sys.exit(__doc__)
    asyncio.run(main(arg))
