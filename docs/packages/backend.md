# Backend packages, in detail

Every Python package the backend uses. Each one follows the same layout:

- **What it is**: the package in general, as you'd explain it to someone new.
- **Why you need it**: the problem it solves in *this* app.
- **What it does here**: where it is used, with the files to open.
- **Without it**: what would break, or what you'd have to write yourself.
- **Alternatives**: what else could do the job, and why this one was picked.
- **Good to know**: gotchas, settings and things that surprised us.

"Range" is the version range from `pyproject.toml`. "Installed" is the version in `backend/.venv` on
2026-11-02. Where a package was chosen by a decision record, the record is linked.

Contents:
[Web & API](#1-web-and-api) ·
[Database](#2-database) ·
[Jobs & caching](#3-jobs-and-caching) ·
[Security](#4-security) ·
[AI](#5-ai) ·
[Files & parsing](#6-files-and-parsing) ·
[Observability](#7-observability) ·
[Optional extras](#8-optional-extras) ·
[Development tools](#9-development-tools) ·
[Pulled in indirectly](#10-packages-you-get-without-asking-for-them)

---

## 1. Web and API

### `fastapi`

Range `>=0.115` · Installed 0.141.1 · Docs: <https://fastapi.tiangolo.com>

**What it is.** A Python web framework for building HTTP APIs. You write ordinary `async def`
functions with type hints, and FastAPI turns them into routes. It validates incoming data against
those types, converts the return value to JSON, and generates interactive API docs automatically.
It is built on Starlette (the web toolkit) and Pydantic (the validation).

**Why you need it.**
- The browser needs an HTTP API for everything: login, uploads, search, Ask, the timeline, people,
  media and the AI Lab.
- The app is async from top to bottom (database, Redis, OpenAI), and FastAPI is async-native.
- Request bodies are checked against Pydantic models before your code runs, so invalid input never
  reaches the database.
- Ask streams its answer as it is written, and FastAPI's `StreamingResponse` supports that.

**What it does here.**
- `app/main.py` creates the app (`create_app()`): CORS middleware, security headers
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), and an exception handler that turns
  "database unreachable" into a clear `503` instead of a bare `500`.
- `app/api/` has one router per resource (`ask.py`, `uploads.py`, `search.py`, `people.py`, …),
  combined in `api/__init__.py`.
- **Dependencies** (`Depends`) inject what a route needs:
  - `get_session` gives each request its own database session (`db/session.py`).
  - `current_user` checks the JWT and loads the user (`auth/security.py`).
  - `rate_limit("ask", 30)` is a dependency that also counts requests (`core/ratelimit.py`).
- `api/ask.py` streams Server-Sent Events with `StreamingResponse`. The agent runs in a background
  task and pushes events into a queue, and a keep-alive is sent every 15 seconds so proxies don't
  close a quiet connection.
- `api/uploads.py` receives files with `UploadFile` and `File(...)`.
- The API docs are at `/api/docs` (Swagger UI) and `/api/openapi.json`.

**Without it.** You'd write routing, validation, JSON conversion, dependency wiring and the docs page
yourself, on top of a lower-level toolkit like Starlette.

**Alternatives.**
- *Flask*: simpler, but synchronous by default, with no built-in validation from type hints.
- *Django + DRF*: a full framework with its own ORM and admin. Heavy for an API-only backend, and
  its async support is partial.
- *Litestar*: similar to FastAPI, but with a smaller community and fewer examples.

**Good to know.**
- Keep route files thin. The real work lives in `ingestion/`, `retrieval/` and `agents/`, which can
  be tested without HTTP.
- In production, `create_app()` refuses to start if `SECRET_KEY` is still the default.
- A dependency can do more than provide a value. `rate_limit` raises `429` before the route body runs.

---

### `uvicorn[standard]`

Range `>=0.30` · Installed 0.53.0 · Docs: <https://www.uvicorn.org>

**What it is.** An **ASGI server**: the program that listens on a port, accepts HTTP connections and
hands each request to your FastAPI app. FastAPI is the app, and uvicorn is what runs it.

**Why you need it.** A FastAPI app can't serve traffic by itself. Something has to own the socket,
run the async event loop and speak HTTP.

**What it does here.**
- Docker runs `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers` after the migrations.
- In development it runs with `--reload`, restarting when you save a file.
- `--proxy-headers` trusts nginx's `X-Forwarded-For` / `X-Forwarded-Proto`, so the app sees the real
  client IP and scheme ([0030](../decisions/0030-nginx-same-origin.md)).

**The `[standard]` extra** adds `uvloop` (a faster event loop, Linux/macOS only), `httptools` (a
faster HTTP parser), `websockets`, `watchfiles` (for `--reload`) and `python-dotenv`. Without it,
uvicorn falls back to slower pure-Python parts.

**Without it.** You'd need another ASGI server.

**Alternatives.** *Hypercorn* (adds HTTP/2 and HTTP/3), *Granian* (written in Rust), or *Gunicorn*
with uvicorn workers (several processes). One uvicorn process is plenty for a single-user app on a
small server.

**Good to know.** It runs one process. If you ever need more, run more containers or add
`--workers N`. Each worker has its own database pool, so watch RDS's connection limit
([0005](../decisions/0005-amazon-rds.md)).

---

### `pydantic[email]`

Range `>=2.7` · Installed 2.13.5 · Docs: <https://docs.pydantic.dev>

**What it is.** A data-validation library. You describe data as a class with type hints, and Pydantic
checks and converts input to match: `"42"` becomes `42`, and a missing field raises an error with a
clear message. Version 2 has a Rust core and is fast.

**Why you need it.**
- Every request and response needs a fixed shape that FastAPI can validate and document.
- AI output is untrusted. When a model is asked for structured output, Pydantic checks the reply
  really has the fields and types the code expects.
- Settings need validation too: a negative token budget should fail at startup, not at 3 a.m.

**What it does here.**
- `schemas/api.py`: request/response models such as `AskIn`, `AskOut` and the login forms.
- `schemas/ai.py`, `retrieval/reranker.py`, `universe/titles.py`: the shapes the models must answer
  in (question analysis, rerank scores, book titles).
- `ai/providers/base.py`: provider types.
- `config/settings.py`: `Field(ge=…, le=…)` limits on settings.

**The `[email]` extra** installs `email-validator`, needed for the `EmailStr` type used on register
and login.

**Without it.** FastAPI requires it. You'd also hand-write checks for every AI reply.

**Alternatives.** *dataclasses* (no validation), *attrs + cattrs*, *marshmallow* (older, separate
schema classes). FastAPI is built on Pydantic, so there's no real choice.

**Good to know.** Pydantic v2's API differs from v1: use `model_validate()` / `model_dump()`, not
`parse_obj()` / `dict()`. Old tutorials often show v1.

---

### `pydantic-settings`

Range `>=2.3` · Installed 2.15.0 · Docs: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>

**What it is.** A Pydantic add-on that fills a model from environment variables and `.env` files.

**Why you need it.** All configuration (API keys, the database URL, limits, model names) comes from
the environment. It needs types (`int`, `bool`, `Literal["llm", "heuristic", "none"]`), defaults and
validation in one place, and it must never reach the browser.

**What it does here.**
- `config/settings.py`: one `Settings` class. The field `openai_api_key` reads the variable
  `OPENAI_API_KEY`, and so on.
- `ENV_FILE` is an absolute path to `backend/.env`, so it's found whichever folder the app starts from.
- Real environment variables (for example from Docker Compose) **override** the `.env` file.
- `extra="ignore"` means unknown variables in `.env` don't crash the app.
- `get_settings()` is wrapped in `lru_cache`, so settings load once per process.
- A validator rewrites `DATABASE_URL` for the async driver ([0005](../decisions/0005-amazon-rds.md)).

**Without it.** You'd read `os.environ` by hand and convert types yourself, with no validation.

**Alternatives.** *python-dotenv* plus manual parsing, *dynaconf*, *environs*.

**Good to know.** Settings are cached, so tests that change environment variables must clear the
cache (`get_settings.cache_clear()`).

---

### `python-multipart`

Range `>=0.0.9` · Installed 0.0.32 · Docs: <https://github.com/Kludex/python-multipart>

**What it is.** A parser for `multipart/form-data`, the encoding browsers use to send files and form fields.

**Why you need it.** Uploads are multipart requests. FastAPI uses this package to read them, and
refuses to start if a route uses `File()` or `Form()` and it isn't installed.

**What it does here.** `api/uploads.py`: `files: list[UploadFile] = File(...)` and
`source_type: str = Form("auto")`. Several files can be uploaded in one request.

**Without it.** No uploads. FastAPI raises an error at startup.

**Alternatives.** None in practice: FastAPI depends on it specifically.

**Good to know.** Uploads are read fully into memory while they're checked and stored, so
`MAX_UPLOAD_MB` (default 50) protects the server's RAM. nginx allows up to 1 GB per request, so
the app's own limit is the one that applies.

---

## 2. Database

### `sqlalchemy[asyncio]`

Range `>=2.0.30` · Installed 2.0.54 · Docs: <https://docs.sqlalchemy.org/en/20/>

**What it is.** Python's most widely used database toolkit. It has two layers:
- **Core**: build SQL in Python (`select(Memory).where(...)`), compiled for your database.
- **ORM**: map Python classes to tables (`class Memory(Base)`), and load and save objects.

The `[asyncio]` extra adds `AsyncSession` and `create_async_engine`.

**Why you need it.**
- About 20 tables, with indexes, foreign keys and PostgreSQL-specific types (`JSONB`, `TSVECTOR`,
  `UUID`, `vector`).
- Queries are built dynamically: optional date filters, person filters, six search paths. Building
  them as Python objects is safer than gluing SQL strings together, and protects against SQL injection.
- The database calls are async, so one slow query doesn't block other requests.

**What it does here.**
- `db/session.py`: the engine (`pool_pre_ping=True`, because hosted databases close idle
  connections), `SessionLocal`, and the `get_session` dependency. `expire_on_commit=False` keeps
  objects readable after commit.
- `models/`: every table. `models/columns.py` has helpers (`uuid_pk`, `user_fk`, `created_at`) so
  every user-owned table is built the same way.
- `models/memory.py`: a computed column, `search_tsv = Computed("to_tsvector('simple', …)")`, which
  PostgreSQL keeps up to date itself, plus GIN and HNSW indexes.
- PostgreSQL's `insert(...).on_conflict_do_nothing()` makes repeated writes safe
  (`ingestion/writer.py`, `universe/pages.py`, `universe/graph.py`).
- Queries everywhere: `retrieval/*.py`, `agents/tools.py`, `api/*.py`.

**Without it.** Raw SQL strings and manual row-to-object mapping, written separately for each query.

**Alternatives.**
- *SQLModel*: SQLAlchemy plus Pydantic in one class. Nice for CRUD, but limiting for complex queries.
- *Tortoise ORM*, *Piccolo*: async-first, with smaller ecosystems and no Alembic.
- *Raw asyncpg*: fastest, but no query builder and no migrations.

**Good to know.**
- `tests/test_sql_compile.py` compiles every query for PostgreSQL **without a database**, so broken
  SQL is caught in the test suite.
- Async sessions don't lazy-load relationships. Load what you need in the query (`selectinload`)
  or you'll get an error.
- A session isn't safe to share between concurrent tasks. That's why streaming Ask opens its own
  session in the background task.

---

### `asyncpg`

Range `>=0.29` · Installed 0.31.0 · Docs: <https://magicstack.github.io/asyncpg/>

**What it is.** A fast async PostgreSQL driver: the low-level library that actually opens the
connection and speaks PostgreSQL's network protocol.

**Why you need it.** SQLAlchemy only builds the queries. It needs a driver to send them, and the
async engine needs an async driver.

**What it does here.** SQLAlchemy uses it whenever the URL starts with `postgresql+asyncpg://`.
`settings.py` adds that prefix to the URL you paste from RDS, and adds `ssl=require` for RDS hosts
([0005](../decisions/0005-amazon-rds.md)).

**Without it.** The async engine can't connect.

**Alternatives.** *psycopg 3* (supports both sync and async, use `postgresql+psycopg://`). Both work.
asyncpg is the most common choice with async SQLAlchemy and is very fast.

**Good to know.** asyncpg takes `ssl=require` in the URL, while psycopg uses `sslmode=require`. The
settings code checks for both so it doesn't add a duplicate.

---

### `alembic`

Range `>=1.13` · Installed 1.20.0 · Docs: <https://alembic.sqlalchemy.org>

**What it is.** The migration tool for SQLAlchemy. A migration is a versioned Python script that
changes the schema (create a table, add a column, add an index). Alembic records which version the
database is at, and applies the missing scripts in order.

**Why you need it.** The schema changes over time (`0002` added cached-token counts, `0003` added the
Memory Universe), and the live database already holds data. You need a repeatable, ordered way to
upgrade it without losing anything.

**What it does here.**
- `alembic/versions/0001_initial.py`: a frozen SQL snapshot that installs the `vector` and `pg_trgm`
  extensions, creates every table and index, and turns on row-level security.
- `0002_cached_input_tokens.py` and `0003_memory_universe.py` follow it.
- `alembic/env.py` connects using the app's settings.
- Docker runs `alembic upgrade head` every time the API container starts.

**Without it.** You'd run SQL scripts by hand and remember which ones each database has had.

**Alternatives.** *yoyo-migrations*, *Flyway* (Java), plain SQL files plus a version table.
Alembic is the standard with SQLAlchemy and can compare models to the database (`--autogenerate`).

**Good to know.**
- Never edit an applied migration. Add a new one:
  `alembic revision --autogenerate -m "describe the change"`, then **read** what it generated.
  Autogenerate misses things like computed columns and extensions.
- Changing the embedding size needs a migration plus re-embedding ([0006](../decisions/0006-embeddings-768.md)).

---

### `pgvector`

Range `>=0.3` · Installed 0.5.0 · Docs: <https://github.com/pgvector/pgvector-python>

**What it is.** There are two things with this name:
1. **pgvector the PostgreSQL extension**: adds a `vector` column type, distance operators and HNSW
   indexes to the database. It must be installed **in the database** (RDS supports it, and the first
   migration runs `CREATE EXTENSION vector`).
2. **`pgvector` the Python package**, the one in `pyproject.toml`: teaches SQLAlchemy about the
   `vector` type, so you can write `Vector(768)` columns and `.cosine_distance(...)` in Python.

**Why you need it.** Semantic search stores a 768-number embedding per memory and asks "which
memories are closest to this question's embedding?". The package lets SQLAlchemy store, read and
query those vectors ([0004](../decisions/0004-postgres-and-pgvector.md)).

**What it does here.**
- `models/memory.py`: `embedding = Vector(768)`, with an HNSW index (`m=16`, `ef_construction=64`,
  `vector_cosine_ops`).
- `retrieval/vector.py`: `Memory.embedding.cosine_distance(query_vector)` (0 = same direction,
  2 = opposite). It also raises `hnsw.ef_search` to 200 and, on pgvector 0.8+, turns on
  `hnsw.iterative_scan`, so filters like "only 2023" don't cut results short.
- `retrieval/books.py`, `universe/books.py`, `universe/graph.py`: book centroids (the average
  embedding of a Memory Book).

**Without it.** You'd write vector SQL as raw strings and convert lists to vector literals yourself.

**Alternatives.** A separate vector database (*Qdrant*, *Weaviate*, *Pinecone*), with its own
hosting, sync and backups. Deferred until benchmarks justify it ([0004](../decisions/0004-postgres-and-pgvector.md)).

**Good to know.**
- HNSW is **approximate**: it may miss a few true nearest neighbours, in exchange for speed.
- Cosine *distance* = 1 − cosine *similarity*. `VECTOR_MIN_SIMILARITY` (0.25) is a similarity.

---

## 3. Jobs and caching

### `redis`

Range `>=5.0` · Installed 5.3.1 · Docs: <https://redis.readthedocs.io>

**What it is.** The official Python client for Redis, an in-memory data store that's very fast for
counters, queues and short-lived values. `redis.asyncio` is its async version.

**Why you need it.** The API and the worker are separate processes. They need **shared** counters
(rate limits, AI request and token budgets) and a shared queue. Process memory can't be shared, but Redis can.

**What it does here.**
- `core/redis.py`: one shared client, plus the "Redis is unreachable" logic: after a failure it's
  skipped for a while instead of every call waiting about 2 seconds for its own timeout.
- `core/ratelimit.py`: fixed-window counters (`INCR`, then `EXPIRE` on the first hit), with keys like
  `rl:ask:<user>:<window>`.
- `ai/usage.py`: daily and monthly request counts and the token budget, shared by every process.
- arq (next section) uses Redis as its queue.

**Without it.** It is **optional** by design ([0018](../decisions/0018-redis-and-arq-optional.md)):
uploads run inside the API process, limits are counted per process, and there is no worker.

**Alternatives.** *Valkey* (an open-source Redis fork, same protocol), *KeyDB*, or database tables
for counters (slower, and they add load to RDS).

**Good to know.** Compose runs `redis:7-alpine` with append-only persistence (`--appendonly yes`), so
queued jobs survive a restart. It is only bound to `127.0.0.1` on the host.

---

### `arq`

Range `>=0.26` · Installed 0.28.0 · Docs: <https://arq-docs.helpmanual.io>

**What it is.** A small **async job queue** built on Redis. Code calls `enqueue_job("ingest", job_id)`,
and a separate worker process picks the job up and runs it. It also supports scheduled (cron) jobs.

**Why you need it.** Importing a large chat takes minutes: parse, hash, normalise, resolve people,
build the graph, embed, analyse sentiment, update the universe. That can't run inside an HTTP request.
The work has to run in the background and survive the browser tab closing.

**What it does here.**
- `workers/queue.py`: `enqueue_ingestion(job_id)` puts the job on the queue, or runs it inline when
  Redis isn't usable.
- `workers/worker.py`: `WorkerSettings` lists the job functions (`ingest`, `build_universe`) and the
  cron jobs:
  - `:00` and `:30`: embed memories that were stored while OpenAI was unavailable
  - `:15` and `:45`: sentiment for memories that don't have it yet
  - `:20` and `:50`: catch up the Memory Universe and name new books
- `max_jobs = 4` jobs at once, each with a one-hour timeout.
- Start it with `arq app.workers.worker.WorkerSettings` (Compose's `worker` service does this).

**Without it.** You'd write your own queue loop on Redis lists, or run imports in-process and lose
them on every restart.

**Alternatives.**
- *Celery*: the most popular, but synchronous at heart and heavy to configure.
- *RQ*: simple, but synchronous.
- *Dramatiq*, *Taskiq*, *SAQ*: viable. Taskiq and SAQ are async-native too.

arq was picked because it is async-native, so jobs reuse the app's async code (async SQLAlchemy,
async OpenAI) unchanged, and it's small enough to read in an afternoon.

**Good to know.** arq jobs are functions that take `ctx` first. Job arguments must be serialisable
(pass a `job_id` string, not a database object).

---

## 4. Security

### `pyjwt`

Range `>=2.8` · Installed 2.15.0 · Docs: <https://pyjwt.readthedocs.io>

**What it is.** Creates and verifies **JSON Web Tokens**: small signed strings that carry claims such
as "user id = …, expires at …". Anyone can read a JWT, but only the holder of the secret key can make
a valid one.

**Why you need it.** After login, the browser must prove who it is on every request without sending
the password again, and the server shouldn't need a session table lookup to check it.

**What it does here.** `auth/security.py`:
- `create_access_token(user_id)` signs `{sub, iat, exp}` with `SECRET_KEY` using **HS256**. Tokens
  last `ACCESS_TOKEN_TTL_MINUTES` (default 7 days).
- `decode_token()` checks the signature and the expiry.
- `current_user` reads `Authorization: Bearer <token>` and loads the user.

**Without it.** You'd implement token signing yourself, which is easy to get subtly wrong.

**Alternatives.** *python-jose*, *authlib* (both bigger), or server-side sessions with cookies (needs
a session store and CSRF protection).

**Good to know.**
- The package is `pyjwt`, but you `import jwt`. **Don't** `pip install jwt`: that's a different,
  unrelated package.
- A JWT can't be revoked before it expires. Logging out clears it in the browser only. Changing
  `SECRET_KEY` invalidates every token.

---

### `bcrypt`

Range `>=4.1` · Installed 5.0.0 · Docs: <https://github.com/pyca/bcrypt>

**What it is.** A password-hashing function that is **deliberately slow** and **salted** (each hash
includes random data). Even if someone steals the database, guessing passwords from the hashes takes
an impractical amount of time.

**Why you need it.** User passwords must never be stored or recoverable in readable form.

**What it does here.** `auth/security.py`: `hash_password()` on register, `verify_password()` on login.

**Without it.** You'd be tempted to use a fast hash like SHA-256, which is unsafe for passwords
because attackers can try billions of guesses per second.

**Alternatives.** *argon2-cffi* (Argon2, the newer recommendation), *passlib* (a wrapper around
several). bcrypt is a solid, widely supported choice.

**Good to know.** bcrypt only uses the first **72 bytes** of a password. Newer bcrypt versions raise
an error on longer input, so the code cuts it to 72 bytes explicitly. Tamil characters take 3 bytes
each in UTF-8, so 72 bytes is 24 Tamil letters.

---

## 5. AI

### `openai`

Range `>=3.19` · Installed 3.19.2 · Docs: <https://platform.openai.com/docs> · <https://github.com/openai/openai-python>

**What it is.** OpenAI's official Python SDK. It handles authentication, retries, timeouts,
streaming and typed responses for every OpenAI API.

**Why you need it.** OpenAI is the AI provider for every task ([0002](../decisions/0002-openai-behind-a-router.md)).
Some of those tasks aren't chat, and LangChain doesn't cover them as well as the SDK does.

**What it does here.**
- `ai/providers/openai.py`: an `AsyncOpenAI` client (created lazily) for:
  - **embeddings**: `text-embedding-3-small`, asked for 768 dimensions, in batches of 256 texts
  - **speech-to-text**: `gpt-4o-mini-transcribe` for uploaded audio
- `finetuning/`: uploading training files, starting fine-tuning jobs, checking their status.
- The SDK retries only once (`max_retries=1`), because the router already retries.

**Without it.** You'd call the REST API with plain HTTP and handle retries, streaming and errors yourself.

**Alternatives.** Use LangChain for embeddings too (`OpenAIEmbeddings`, which the evaluation code
does), or plain `httpx`.

**Good to know.** Model names change as OpenAI retires models. They're all in settings, so you can
switch models without code changes. Changing the **embedding** model means re-embedding everything.

---

### `langchain-core`

Range `>=1.6` · Installed 1.6.4 · Docs: <https://python.langchain.com>

**What it is.** The base layer of LangChain: standard interfaces for chat models (`BaseChatModel`),
messages (`SystemMessage`, `HumanMessage`, `AIMessage`), streaming, structured output and
"runnables" (composable steps). Provider packages like `langchain-openai` implement these interfaces.

**Why you need it.** It gives one interface for every chat model, so the rest of the code doesn't
care which model is behind it, and it's the base LangGraph builds on.

**What it does here.**
- `ai/providers/langchain_utils.py`: converts the app's simple `("system", "…")` tuples to LangChain
  messages, streams text (`model.astream`), and adds up token usage (`usage_metadata`, including
  `cache_read` for prompt-cache hits) across streamed chunks.
- `agents/graph.py`: `RunnableConfig`, which passes callbacks and tracing through the agent.

**Without it.** You'd write your own message types and streaming adapters for each provider.

**Alternatives.** The provider SDK directly, *LiteLLM* (one API for many providers), *Pydantic AI*.

**Good to know.** LangChain changed a lot between versions. Make sure examples you read are for
1.x and `langchain-core`, not the old all-in-one `langchain` 0.0.x package.

---

### `langchain-openai`

Range `>=1.6` · Installed 1.6.6 · Docs: <https://python.langchain.com/docs/integrations/chat/openai/>

**What it is.** LangChain's integration for OpenAI: `ChatOpenAI` (a chat model) and `OpenAIEmbeddings`.

**Why you need it.** Every chat call (answers, question analysis, reranking, verification, book
titles, fine-tuning labels) goes through `ChatOpenAI`, so it gets LangChain's structured output,
streaming and automatic LangSmith tracing.

**What it does here.**
- `ai/providers/openai.py`: one `ChatOpenAI` per (task, temperature), cached in `_chat_models`, so
  the reasoning model writes answers and the fast model does quick jobs.
- `evaluation/runner.py`: `ChatOpenAI` and `OpenAIEmbeddings` wrapped for RAGAS.

**Without it.** Chat calls would go through the raw SDK, losing the LangChain interface and tracing.

**Alternatives.** The `openai` SDK's own `chat.completions` / `responses` API.

**Good to know.** Prompt caching ([0017](../decisions/0017-prompt-caching.md)) works through
`ChatOpenAI` because OpenAI caches automatically. The app only has to keep prompts fixed-first and
send a `prompt_cache_key`.

---

### `langchain-text-splitters`

Range `>=1.1` · Installed 1.1.2 · Docs: <https://python.langchain.com/docs/concepts/text_splitters/>

**What it is.** Text chunkers: split long text into pieces small enough to embed and cite.

**Why you need it.** One embedding for a 30-page PDF is too blurry to match a specific question,
and the evidence card would have to show the whole PDF. Chunks fix both problems
([0022](../decisions/0022-documents-chunking.md)).

**What it does here.** `ingestion/parsers/documents.py`: `RecursiveCharacterTextSplitter` with
1,200-character chunks and 150 characters of overlap. It tries to break at paragraphs first, then
sentences, then words.

**Without it.** You'd write a splitter yourself, which is fiddly at the edges.

**Alternatives.** *semchunk*, *chonkie*, or splitting on headings yourself (which the journal parser
already does for dated headings).

**Good to know.** It's imported inside the function, so the package only loads when a document is
actually parsed.

---

### `langgraph`

Range `>=0.2` · Installed 1.2.12 · Docs: <https://langchain-ai.github.io/langgraph/>

**What it is.** A library for building **stateful, multi-step** LLM workflows as a graph. Nodes are
steps (functions), edges decide what runs next (including loops), and a typed state object is passed
along and updated.

**Why you need it.** Answering a question isn't one prompt. It's analyse → retrieve → verify →
*maybe retrieve again* → answer, with progress reported as it goes. That loop with state is what
LangGraph is for ([0003](../decisions/0003-langgraph-and-langchain.md)).

**What it does here.** `agents/graph.py`: a `StateGraph` with `START → analyze → retrieve → verify
→ (retrieve | answer) → END`. Each node calls tools (`agents/tools.py`) or the router, and emits
progress events that `api/ask.py` streams to the browser.

**Without it.** A hand-written loop with if-statements. That works for a small agent, but the steps,
state and tracing are harder to see and test.

**Alternatives.** *Plain Python*, *Pydantic AI*, *LlamaIndex Workflows*, *CrewAI* (multi-agent, ruled
out as a second orchestration layer).

**Good to know.** The `pyproject.toml` floor is low (`>=0.2`), but 1.x is installed. Read the 1.x
docs, because the API changed.

---

### `httpx`

Range `>=0.27` · Installed 0.28.1 · Docs: <https://www.python-httpx.org>

**What it is.** A modern HTTP client for Python, with sync and async APIs, timeouts and connection pooling.

**Why you need it.** The OpenAI SDK makes all its requests with httpx. It's listed directly because
the app's code uses it too.

**What it does here.** `OpenAIProvider(settings, http_client=…)` accepts an `httpx.AsyncClient`.
In production it's `None` and the SDK makes its own. In `tests/test_openai.py` a client with a fake
**transport** plays the OpenAI server, so the provider is tested end to end with no network and no key.

**Without it.** The OpenAI SDK would still install it, but the tests couldn't inject a fake server
as cleanly.

**Alternatives.** *aiohttp* (async only), *requests* (sync only).

**Good to know.** httpx's `MockTransport` is a great way to test any code that makes HTTP calls.

---

### `numpy`

Range `>=1.26` · Installed 2.5.3 · Docs: <https://numpy.org/doc/>

**What it is.** Python's numeric-array library: fast maths on whole arrays of numbers at once.

**Why you need it.** Some vector maths happens in Python rather than in the database, after the
candidates are loaded.

**What it does here.**
- `retrieval/diversity.py`: MMR compares every candidate's embedding with the ones already picked
  (cosine similarity in matrix form) ([0008](../decisions/0008-reranking-stages.md)).
- `universe/matching.py`: book centroids and "does this page belong to that book?" similarity.
- Tests: `test_reranking.py`, `test_universe.py`.

**Without it.** Pure-Python loops over 768-number lists, about 100× slower.

**Alternatives.** None worth it. pgvector already requires numpy too.

---

## 6. Files and parsing

### `boto3`

Range `>=1.34` · Installed 1.43.101 · Docs: <https://boto3.amazonaws.com/v1/documentation/api/latest/index.html>

**What it is.** The official AWS SDK for Python. It talks to every AWS service, including DynamoDB.

**Why you need it.** Media files live in a DynamoDB table in the standard setup
([0019](../decisions/0019-media-in-dynamodb.md)).

**What it does here.** `media/storage.py` → `DynamoDBStorage`:
- `put` splits a file into 350 KB chunks (DynamoDB's item limit is 400 KB) and writes them with
  `BatchWriteItem`.
- `get` reads every chunk with `Query` (`boto3.dynamodb.conditions.Key`) and joins them.
- `create-table` (`python -m app.media.storage create-table`) creates the table once.
- Credentials come from `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, or boto3's usual chain
  (environment, `~/.aws/credentials`, an IAM role).

**Without it.** No DynamoDB storage. `STORAGE_BACKEND=local` would still work.

**Alternatives.** *aioboto3* (async boto3), or the raw HTTP API.

**Good to know.** boto3 is **synchronous**. Every call is wrapped in `asyncio.to_thread(...)`, so a
slow upload doesn't block the event loop. In tests, `moto` fakes DynamoDB (see
[Development tools](#9-development-tools)).

---

### `pypdf`

Range `>=4.2` · Installed 6.19.0 · Docs: <https://pypdf.readthedocs.io>

**What it is.** A pure-Python library for reading (and writing) PDF files, with no system dependencies.

**Why you need it.** Users upload PDFs (notes, tickets, letters), and their text has to become searchable memories.

**What it does here.** `ingestion/parsers/documents.py`: `PdfReader` extracts the text page by page,
and then it's chunked ([0022](../decisions/0022-documents-chunking.md)).

**Without it.** PDF uploads would be rejected or stored without text.

**Alternatives.** *pdfplumber* (better tables, slower), *PyMuPDF* (fast, but AGPL-licensed),
*unstructured* (heavy). pypdf keeps the image small and has no native dependencies.

**Good to know.** Scanned PDFs are images, with no text to extract. OCR isn't built.

---

### `python-docx`

Range `>=1.1` · Installed 1.2.0 · Docs: <https://python-docx.readthedocs.io>

**What it is.** Reads and writes Microsoft Word `.docx` files.

**Why you need it.** Same reason as pypdf, for Word documents.

**What it does here.** `ingestion/parsers/documents.py`: `import docx`, then it reads the paragraphs
and chunks them.

**Without it.** No `.docx` uploads.

**Alternatives.** *docx2txt*, *mammoth* (to HTML).

**Good to know.** The package is `python-docx`, but you `import docx`. Old `.doc` files (pre-2007
Word) aren't supported.

---

### `pillow`

Range `>=10` · Installed 12.3.0 · Docs: <https://pillow.readthedocs.io>

**What it is.** The standard Python imaging library (a fork of PIL). It opens, edits and saves images,
and reads their metadata.

**Why you need it.** A photo's place on the timeline comes from its EXIF "date taken"
([0021](../decisions/0021-photos-metadata-only.md)).

**What it does here.** `ingestion/photos.py`: `Image.open()` reads only the **header**. It reads the
EXIF tags `DateTimeOriginal` (0x9003), `DateTime` (0x0132) and the EXIF sub-block (0x8769). The
pixels are never decoded.

**Without it.** Photos could only be dated from file names and upload times.

**Alternatives.** *exifread*, *piexif* (EXIF only). Pillow is already the standard and handles every format.

**Good to know.** `Image.open()` is lazy: it parses the header and doesn't load pixels until you ask.
That's what makes "metadata only" cheap.

---

### `tzdata`

Range `>=2024.1` · Installed 2026.4 · Docs: <https://tzdata.readthedocs.io>

**What it is.** The IANA timezone database (the rules for `Asia/Kolkata`, `Europe/London`, …) packaged for Python.

**Why you need it.** Chat exports have no timezone, so their times are read in `DEFAULT_TIMEZONE`
(`Asia/Kolkata`) with Python's `zoneinfo`. Linux has the database built in. **Windows doesn't**, so
without this package `ZoneInfo("Asia/Kolkata")` fails on Windows.

**What it does here.** `core/timeutils.py`: `ZoneInfo(...)` finds its data here when the OS has none.

**Without it.** Local development on Windows crashes on the first date.

**Alternatives.** *pytz* (older API, not needed since Python 3.9).

**Good to know.** Timezone rules change (countries change their clocks), so keep it updated.

---

## 7. Observability

### `opentelemetry-api` and `opentelemetry-sdk`

Range `>=1.25` · Installed 1.44.0 · Docs: <https://opentelemetry.io/docs/languages/python/>

**What it is.** OpenTelemetry is the open standard for **traces** (and metrics and logs). A trace is a
tree of **spans**, each a timed step ("vector search: 42 ms"). The **API** is what code calls to
create spans. The **SDK** is the implementation that collects spans and sends them somewhere.

**Why you need it.** To see where time goes in a slow answer, across the API, the database and
OpenAI, in a standard tool such as Jaeger, Grafana Tempo or Honeycomb ([0028](../decisions/0028-observability.md)).

**What it does here.**
- `observability/tracing.py`: `tracer = trace.get_tracer("memory-engine")`. `StepTimer` records each
  agent step for the user-visible trace **and** emits a span.
- `setup_tracing()` does nothing unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. When it is, it creates
  a `TracerProvider` with a batch exporter.
- `ai/providers/router.py` wraps every AI call in a span.

**Without it.** No external tracing. The user-visible trace could still be built by hand.

**Alternatives.** Vendor SDKs (Datadog, New Relic), which lock you to one vendor.

**Good to know.** With only the API installed and no SDK setup, every span is a **no-op**, which is
cheap. That's why the code can call `tracer` everywhere unconditionally.

---

## 8. Optional extras

Install with `pip install -e ".[otel]"`, `".[sentiment]"`, `".[eval]"` or `".[dev]"`, or several
at once: `".[dev,sentiment]"`.

### `otel` extra: `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`

Docs: <https://opentelemetry.io/docs/languages/python/exporters/>

- **The exporter** sends spans over OTLP (OpenTelemetry's protocol) to a collector at
  `OTEL_EXPORTER_OTLP_ENDPOINT`. Without it, spans are created but go nowhere.
- **The FastAPI instrumentation** adds a span for every HTTP request automatically (method, path,
  status code, duration), with the agent spans nested inside.
- **Why it's an extra:** most local development doesn't need it. Docker always installs it
  (`requirements.txt`), so production can turn it on with one environment variable.
- If the endpoint is set but the extra is missing, the app logs a warning and keeps running.

### `sentiment` extra: `transformers`, `torch`

Range `transformers>=4.44`, `torch>=2.2` · Installed 5.17.0, 2.14.0+cpu
Docs: <https://huggingface.co/docs/transformers> · <https://pytorch.org/docs>

**What they are.**
- **PyTorch (`torch`)** is a deep-learning framework: tensors (multi-dimensional arrays) and the maths
  to run neural networks on a CPU or GPU.
- **Hugging Face `transformers`** loads pre-trained models from the Hugging Face Hub and runs them.
  `pipeline("text-classification", model=…)` gives you a ready classifier in one line.

**Why you need them.** The sentiment model, `vishnuexe/TamilSense-model` (MuRIL fine-tuned on Tamil
and Tanglish), is a PyTorch model loaded with transformers ([0023](../decisions/0023-local-sentiment-model.md)).

**What they do here.**
- `sentiment/model.py`: loads the pipeline once per process, under a lock so two threads don't load
  it twice. It classifies in batches of 32, truncates to 512 tokens, and maps `LABEL_0` / `LABEL_1`
  to positive / negative.
- The work is CPU-heavy and blocking, so callers use `asyncio.to_thread(classify, texts)`.

**Why they're an extra.** They're huge. Default PyTorch includes about 2 GB of GPU (CUDA) libraries.
Docker installs the **CPU-only** wheel from `https://download.pytorch.org/whl/cpu`, and the free-tier
image leaves both out ([0031](../decisions/0031-backend-docker-image.md), [0032](../decisions/0032-free-tier-deployment.md)).

**Without them.** Sentiment is skipped and everything else works (`SentimentUnavailable` is caught).

**Good to know.**
- The first load downloads about 1 GB into the Hugging Face cache (`HF_HOME`, `/app/hf-cache` in Docker).
- For a CPU-only torch outside Docker, install it first:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

### `eval` extra: `ragas`, `datasets`

Docs: <https://docs.ragas.io> · <https://huggingface.co/docs/datasets>

**What they are.**
- **RAGAS** scores RAG answers with LLM-based metrics: *faithfulness* (is the answer supported by
  the evidence?), *context precision* and *context recall*, and *response relevancy*.
- **`datasets`** is Hugging Face's table format. RAGAS uses it internally.

**Why you need them.** To grade the agent's answers, not just retrieval, on your own golden set
([0027](../decisions/0027-evaluation.md)).

**What they do here.** `evaluation/runner.py`: builds an `EvaluationDataset`, wraps `ChatOpenAI`
and `OpenAIEmbeddings` with RAGAS's LangChain wrappers, and runs `Faithfulness`,
`LLMContextPrecisionWithReference`, `LLMContextRecall` and `ResponseRelevancy`. Imported inside the
function, so the runner works without them for the other metrics.

**Why they're an extra.** Only needed when evaluating, and they pull in many dependencies. They
aren't installed in `.venv` right now.

---

## 9. Development tools

The `dev` extra: `pip install -e ".[dev]"`. Never installed in Docker.

### `pytest`

Range `>=8` · Installed 9.1.1 · Docs: <https://docs.pytest.org>

**What it is.** Python's standard test runner. Tests are plain functions named `test_…` using plain
`assert`, and **fixtures** provide shared setup.

**Why you need it.** About 17 test files cover parsers, multilingual rules, retrieval, the agent,
the router, storage and SQL compilation, so changes can be made safely.

**What it does here.** `backend/tests/`, run with `.venv/Scripts/pytest -q`. Config is in
`pyproject.toml` (`testpaths = ["tests"]`), and shared fixtures are in `tests/conftest.py`. The tests
need **no database, Redis, API keys or AWS account**: OpenAI and DynamoDB are faked.

### `pytest-asyncio`

Range `>=0.23` · Installed 1.4.0 · Docs: <https://pytest-asyncio.readthedocs.io>

**What it is.** Lets pytest run `async def` tests.

**Why you need it.** Most of the app is async, and so are its tests.

**Good to know.** `asyncio_mode = "auto"` in `pyproject.toml` means every async test runs
automatically, with no `@pytest.mark.asyncio` needed.

### `ruff`

Range `>=0.5` · Installed 0.16.8 · Docs: <https://docs.astral.sh/ruff/>

**What it is.** An extremely fast Python **linter** and **formatter**, written in Rust. It replaces
flake8, isort, pyupgrade and more.

**Why you need it.** It catches bugs (unused variables, undefined names, risky patterns) and keeps
imports sorted and the style consistent.

**What it does here.** Config in `pyproject.toml`: line length 140, target Python 3.11. Rule sets:
`E` (style), `F` (pyflakes: real errors), `I` (import order), `UP` (modern syntax), `B` (bugbear:
likely bugs), `PLE` (pylint errors), `RUF100` (unused `noqa`). `B008` is ignored because FastAPI's
`Depends()` defaults are the framework idiom.

Run it with `.venv/Scripts/ruff check .` and `.venv/Scripts/ruff format .`.

### `moto[dynamodb]`

Range `>=5` · Installed 5.2.3 · Docs: <https://docs.getmoto.org>

**What it is.** A library that **fakes AWS services** in memory. boto3 calls go to moto instead of AWS.

**Why you need it.** To test the DynamoDB storage (chunking, reassembly, deletion) without an AWS
account, network access or cost.

**What it does here.** `tests/test_storage.py`. `[dynamodb]` installs only what the DynamoDB fake needs.

---

## 10. Packages you get without asking for them

These aren't in `pyproject.toml`, but you'll see them in `pip list` and in the code:

| Package | Comes with | What it is |
|---|---|---|
| `starlette` | FastAPI | The web toolkit FastAPI is built on: routing, middleware, `StreamingResponse` |
| `email-validator` | `pydantic[email]` | Checks email addresses for `EmailStr` |
| `langsmith` | `langchain-core` | The LangSmith tracing client. Tracing turns on when `LANGSMITH_API_KEY` is set ([0028](../decisions/0028-observability.md)) |
| `uvloop`, `httptools`, `watchfiles` | `uvicorn[standard]` | A faster event loop, a faster HTTP parser, and auto-reload |
| `setuptools` | the build system | Turns `backend/` into the installable package `memory-engine` (only `app*` packages) |

To see why any package is installed: `.venv/Scripts/pip show <name>` (look at `Required-by`).
