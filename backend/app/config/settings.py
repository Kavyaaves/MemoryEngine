"""All configuration, read from environment variables or a `.env` file (see .env.example).

Field `openai_api_key` ⇄ variable OPENAI_API_KEY, and so on (names are case-insensitive).
API keys live only here, on the server — they are never sent to the browser.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env — found the same way no matter which folder the app is started from.
# (Real environment variables, e.g. from docker compose, take priority over this file.)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def to_async_database_url(url: str) -> str:
    """Accept the connection string exactly as Amazon RDS (or any Postgres host) shows it.

    'postgresql://user:pass@host:5432/db'  →  'postgresql+asyncpg://user:pass@host:5432/db?ssl=require'
    - SQLAlchemy needs the '+asyncpg' part to know which driver to use.
    - RDS for PostgreSQL 15+ only accepts encrypted connections, so ssl=require is added for its
      hosts (*.rds.amazonaws.com).
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    host = urlsplit(url).hostname or ""
    if host.endswith(".rds.amazonaws.com") and "ssl=" not in url and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "ssl=require"
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    environment: Literal["development", "staging", "production"] = "development"
    secret_key: str = "change-me-in-production"  # signs login tokens and local media links
    access_token_ttl_minutes: int = 60 * 24 * 7
    cors_origins: list[str] = ["http://localhost:5173"]
    default_timezone: str = "Asia/Kolkata"  # chat exports have no timezone; dates are read in this one
    processing_version: int = 1  # bump when ingestion logic changes, to find memories to re-process

    # --- Database (Amazon RDS for PostgreSQL 15+, with the pgvector extension) ---
    database_url: str = "postgresql+asyncpg://memory:memory@localhost:5432/memory"
    # Connections per process (the API and the worker each have their own pool). A small RDS
    # instance allows only about 80 connections in total, so keep these small.
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # --- Job queue ---
    # Empty = run without Redis: uploads are processed in the API process and limits are counted
    # per process (see core/redis.py). The background worker needs Redis.
    redis_url: str = "redis://localhost:6379/0"
    inline_ingestion: bool = False  # true = process uploads inside the API process (no worker needed)

    # --- Hosted AI: OpenAI (the only local model is the sentiment one, further down) ---
    openai_api_key: str | None = None
    # OpenAI retires models over time; see https://platform.openai.com/docs/models for what your key can use.
    openai_reasoning_model: str = "gpt-4.1-mini"  # writes the answers
    openai_fast_model: str = "gpt-4.1-nano"  # quick jobs: understanding the question, checking evidence, reranking
    # No vision model: photos are never sent to an AI model (ingestion/photos.py).
    openai_speech_model: str = "gpt-4o-mini-transcribe"  # audio → text
    # Embeddings (text → vector for semantic search) always come from OpenAI: vectors from two
    # different models can't be compared. Changing the model after importing data makes the
    # backfill re-embed every memory.
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 768  # must match the vector(768) column created by the migration
    embedding_batch_size: int = 256  # texts per API request
    # Below this cosine similarity a semantic match counts as noise. A starting point for
    # text-embedding-3-small (unrelated texts score about 0.1-0.2); tune it with app.evaluation.runner.
    vector_min_similarity: float = 0.25

    # --- Fine-tuning phase (app/finetuning/) ---
    # base:    the standard model the very first training run starts from (a dated snapshot)
    # derived: the model we trained. Every new run continues from it. Empty = none trained yet, and
    #          the app uses its no-AI baselines. `python -m app.finetuning status` prints the value.
    finetune_base_model: str = "gpt-4.1-nano-2025-04-14"
    finetune_derived_model: str | None = None  # e.g. "ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123"
    finetune_teacher_model: str = "gpt-4.1"  # a bigger model that labels the training examples

    # --- Sentiment (app/sentiment/) — the one LOCAL model: runs on this machine's CPU, nothing is sent out ---
    # Included in the Docker image. Locally it needs the optional extra:  pip install -e ".[sentiment]"
    # (without it, sentiment is simply skipped). In Docker the model is baked in at build time — if you
    # change sentiment_model, rebuild with the matching SENTIMENT_MODEL build arg (see backend/Dockerfile).
    sentiment_enabled: bool = True
    sentiment_model: str = "vishnuexe/TamilSense-model"  # Hugging Face: Tamil + Tanglish, labels positive / negative
    sentiment_batch_size: int = 32  # texts per model call
    # The model only knows positive and negative. Below this confidence a text counts as "neutral" ("ok da").
    sentiment_neutral_below: float = Field(default=0.75, ge=0.5, le=1.0)

    @property
    def embedding_model(self) -> str:
        """The model whose name is stored next to each vector."""
        return self.openai_embedding_model

    # --- Limits (quota guard + uploads) ---
    max_daily_requests: int = 1500  # per AI provider
    max_monthly_requests: int = 30000
    # Token budget: at most this many tokens (input + output) every `token_window_hours` hours.
    # One question uses roughly 10,000 tokens (understand, rerank, verify, answer). 0 = no budget.
    max_tokens_per_window: int = Field(default=2_000_000, ge=0)
    token_window_hours: int = Field(default=24, ge=1)  # 24 = resets at midnight UTC; 1 = hourly
    max_upload_mb: int = 50  # each upload is held in memory while it is checked and stored
    max_image_mb: int = 20

    # --- Retrieval ---
    retrieval_top_k: int = 12  # results returned
    retrieval_candidates_per_path: int = 50  # candidates each search path contributes
    rrf_k: int = 60  # reciprocal rank fusion constant (see retrieval/fusion.py)
    # How the merged candidates are re-ordered (retrieval/reranker.py):
    #   llm        heuristic first, then the fast OpenAI model scores the top 20 (falls back to heuristic)
    #   heuristic  cheap signals only (term coverage, phrase match, path agreement, similarity)
    #   none       keep the fusion order — only useful as an evaluation baseline
    reranker: Literal["none", "heuristic", "llm"] = "llm"
    # Maximal Marginal Relevance (retrieval/diversity.py): 1.0 = off (pure relevance); lower values
    # push near-duplicate memories (e.g. the same forwarded message) down the list. Try 0.7.
    mmr_lambda: float = Field(default=1.0, ge=0.0, le=1.0)

    # --- File storage (uploads, photos, audio, video) ---
    #   dynamodb: an Amazon DynamoDB table (AWS's always-free tier includes 25 GB of storage)
    #   local:    a folder on this machine — development and tests only
    storage_backend: Literal["dynamodb", "local"] = "dynamodb"
    aws_region: str = "ap-south-1"  # Mumbai; keep it the same as the RDS database
    # Leave both empty to use boto3's usual credentials (environment, ~/.aws/credentials or an IAM role).
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    dynamodb_media_table: str = "memory-engine-media"  # create it with: python -m app.media.storage create-table
    local_storage_dir: str = "./data/objects"

    # --- Observability (optional) ---
    otel_exporter_otlp_endpoint: str | None = None
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = True
    langsmith_project: str = "memory-engine"

    @field_validator("database_url")
    @classmethod
    def _use_async_driver(cls, url: str) -> str:
        return to_async_database_url(url)


@lru_cache
def get_settings() -> Settings:
    """The settings, loaded once and cached."""
    return Settings()
