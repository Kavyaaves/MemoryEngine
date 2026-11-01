"""The background worker. Start it with:  arq app.workers.worker.WorkerSettings

It picks ingestion jobs and universe builds off the Redis queue (see queue.py), and every
30 minutes embeds any memories that were stored while no embedding provider was available.
At :15 and :45 it analyses the sentiment of memories that don't have one yet; at :20 and :50
it catches up the Memory Universe (places any unplaced memories, names books with AI).
"""

from arq import cron

from app.ai.embeddings import backfill
from app.ingestion.pipeline import build_universe as build_universe_for_user
from app.ingestion.pipeline import process_job
from app.sentiment.pipeline import backfill as backfill_sentiment_of_memories
from app.universe.__main__ import build_all as build_universe_for_everyone
from app.universe.titles import name_books
from app.workers.queue import redis_settings


async def ingest(ctx, job_id: str) -> None:
    await process_job(job_id)


async def build_universe(ctx, user_id: str) -> None:
    await build_universe_for_user(user_id)


async def catch_up_universe(ctx) -> int:
    await build_universe_for_everyone()
    return await name_books()


async def backfill_embeddings(ctx) -> int:
    return await backfill(max_wait_minutes=10)


async def backfill_sentiment(ctx) -> int:
    return await backfill_sentiment_of_memories()


class WorkerSettings:
    functions = [ingest, build_universe]
    cron_jobs = [cron(backfill_embeddings, minute={0, 30}), cron(backfill_sentiment, minute={15, 45}),
                 cron(catch_up_universe, minute={20, 50})]
    redis_settings = redis_settings()
    max_jobs = 4
    job_timeout = 60 * 60  # a very large chat export can take a while
