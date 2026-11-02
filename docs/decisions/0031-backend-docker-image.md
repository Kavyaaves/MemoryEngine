# 0031. One backend image for the API and the worker, layered for fast rebuilds

- **Status:** Accepted
- **Date:** 2026-11-02 (`requirements.txt` and the `WITH_SENTIMENT` build argument)

## Context

The API and the worker run the same code with different commands. The sentiment model and PyTorch
are huge (about 1.5 GB) and change rarely, while the app code changes all the time. Docker reuses a
layer only if nothing before it changed, so the order of steps decides how slow a rebuild is.

## Decision

- **One image**, `python:3.12-slim`. The API runs `alembic upgrade head` then uvicorn. The worker
  service overrides the command with `arq app.workers.worker.WorkerSettings`.
- **Layer order**, slowest-changing first:
  1. a non-root user `memory` (uid 1000), created first so the model downloads straight as that user.
     A `chown -R` afterwards would copy the 1 GB model into a second layer.
  2. CPU-only PyTorch (the default wheel adds about 2 GB of GPU libraries a CPU server never uses)
     and transformers
  3. the sentiment model, downloaded at build time so containers start ready and never need Hugging Face
  4. `requirements.txt`, the Python dependencies
  5. the app code, installed with `pip install --no-deps .`
- **`WITH_SENTIMENT=false`** skips steps 2 and 3 for a small image of about 500 MB.
- **`requirements.txt`** lists `pyproject.toml`'s dependencies plus the `otel` extra. It exists so
  step 4 is cached: editing code no longer reinstalls every dependency. Keep it in sync with `pyproject.toml`.
- Migrations run on start, so a deploy is "build and start".
- `.dockerignore` keeps `.env`, `.venv`, tests, private eval data and `*.pem` keys out of the build.

## Consequences

- Code-only changes rebuild in seconds. Changing `SENTIMENT_MODEL` needs a rebuild with the matching
  build argument.
- A new Python package must be added to both `pyproject.toml` and `requirements.txt`.
- The full image is about 2.5 GB. Give Docker at least 4 GB of RAM.

## Where in the code

`backend/Dockerfile`, `backend/requirements.txt`, `backend/.dockerignore`, `docker-compose.yml`.
