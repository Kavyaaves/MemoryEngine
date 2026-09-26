"""Analyse the sentiment of every memory that doesn't have one yet:

    python -m app.sentiment

Safe to stop (Ctrl+C) and run again — it continues where it left off.
"""

import asyncio
import logging

from app.sentiment.pipeline import backfill

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(backfill(progress=print))
