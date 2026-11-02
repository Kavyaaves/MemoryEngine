# Packages and services

Everything the app depends on: what each piece is, why it's needed, what it does here, and what to
watch out for.

| Guide | Covers |
|---|---|
| [backend.md](backend.md) | every Python package: runtime, the optional extras (`otel`, `sentiment`, `eval`) and the dev tools |
| [frontend.md](frontend.md) | every npm package: React, data and state, 3D, styling, build tools, types |
| this page | Docker images, hosted services, and how to add, upgrade or remove a package |

## The whole stack on one screen

```
Browser   React 19 · React Router · TanStack Query · Zustand · Tailwind v4 · three.js + R3F + drei
            │  built by Vite + TypeScript, served by nginx
            ▼
API       FastAPI on uvicorn · Pydantic · pyjwt + bcrypt
            ├─ database   SQLAlchemy (async) → asyncpg → PostgreSQL on RDS (pgvector, pg_trgm, FTS) · Alembic
            ├─ jobs       arq → Redis ← redis (rate limits, AI budgets)
            ├─ AI         LangGraph agent → LangChain (ChatOpenAI) / openai SDK → OpenAI
            ├─ files      boto3 → DynamoDB (or local disk) · pypdf · python-docx · Pillow (EXIF only)
            ├─ local ML   transformers + torch (CPU) → TamilSense sentiment   [optional]
            └─ tracing    OpenTelemetry (→ OTLP) · LangSmith                   [optional]
```

## Docker images

| Image | Where | Why this one |
|---|---|---|
| `python:3.12-slim` | `backend/Dockerfile` (API and worker) | Debian-based "slim": small, but with glibc, so prebuilt wheels like torch, numpy and asyncpg install without compiling. Alpine uses musl, where many wheels must be built from source |
| `node:24-alpine` | `frontend/Dockerfile`, build stage only | Node is only needed to build. Alpine keeps it small, and it is thrown away after `npm run build` |
| `nginx:1.27-alpine` | `frontend/Dockerfile`, serve stage | Serves static files and proxies `/api` with SSE buffering off ([0030](../decisions/0030-nginx-same-origin.md)) |
| `redis:7-alpine` | `docker-compose.yml` | The job queue and counters, with append-only persistence so queued jobs survive a restart |

Multi-stage builds: the frontend image contains only nginx and the built files, not Node or
`node_modules`. The backend is single-stage, but ordered so slow layers are cached
([0031](../decisions/0031-backend-docker-image.md)).

## Hosted services

These aren't packages, but the app depends on them just as much.

| Service | Used for | Needed? | Decision |
|---|---|---|---|
| OpenAI API | answers, reranking, question analysis, embeddings, transcription, fine-tuning | for AI features. Without it the app degrades to keyword search and extractive answers | [0002](../decisions/0002-openai-behind-a-router.md) |
| Amazon RDS for PostgreSQL | the database | yes | [0005](../decisions/0005-amazon-rds.md) |
| Amazon DynamoDB | media files (standard setup) | no: `STORAGE_BACKEND=local` uses disk | [0019](../decisions/0019-media-in-dynamodb.md) |
| Hugging Face Hub | downloading the sentiment model | only at Docker build time (or the first local load) | [0023](../decisions/0023-local-sentiment-model.md) |
| LangSmith | tracing LangChain / LangGraph runs | no: on when `LANGSMITH_API_KEY` is set | [0028](../decisions/0028-observability.md) |
| An OTLP collector (Jaeger, Tempo, Honeycomb, …) | OpenTelemetry traces | no: on when `OTEL_EXPORTER_OTLP_ENDPOINT` is set | [0028](../decisions/0028-observability.md) |

## Adding, upgrading or removing a package

### Backend

1. Add it to `backend/pyproject.toml`: `dependencies` for runtime, or an extra in
   `[project.optional-dependencies]` if only some setups need it.
2. If it's a runtime dependency, **also add it to `backend/requirements.txt`**. Docker installs from
   that file, so a package missing from it will be missing from the image ([0031](../decisions/0031-backend-docker-image.md)).
3. Install locally: `.venv/Scripts/pip install -e ".[dev]"`.
4. Run the tests: `.venv/Scripts/pytest -q`.
5. Rebuild the image: `docker compose build backend`.
6. Add it to [backend.md](backend.md).

Upgrading: raise the floor in **both** files only when you need something new. The floors are
minimums (`>=`), so a fresh install always gets the newest version allowed. After a major upgrade
(SQLAlchemy, Pydantic, LangChain, LangGraph), read the changelog, because these libraries rename APIs
between majors.

Removing: search for the import first (`import x` / `from x`), and remember some packages are
imported under a different name: `pyjwt` → `jwt`, `python-docx` → `docx`, `pillow` → `PIL`.

### Frontend

1. `npm install <name>` (or `npm install -D <name>` for build-only tools). This updates
   `package.json` and `package-lock.json`. Commit both.
2. `npm run typecheck` and `npm run build`.
3. Add it to [frontend.md](frontend.md).

Keep pairs in step: `three` with `@types/three`, `react` with `@types/react`, and React 19 with
React Three Fiber 9.

### Checking what's installed

```bash
cd backend && .venv/Scripts/pip list
```

```bash
cd backend && .venv/Scripts/pip show sqlalchemy
```

```bash
cd frontend && npm ls --depth=0
```

`pip show` lists `Requires` and `Required-by`, which tells you why a package is there.
