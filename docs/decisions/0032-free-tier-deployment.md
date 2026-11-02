# 0032. A free-tier deployment on one t3.micro

- **Status:** Accepted
- **Date:** 2026-11-02

## Context

The standard Compose setup needs about 4 GB of RAM (the sentiment model takes about 1 GB per
container) and stores media in DynamoDB with on-demand capacity, which the free tier doesn't cover.
The goal was a deployment where OpenAI is the only paid part.

## Decision

An override file, `docker-compose.free.yml`, used on top of the normal one:

    docker compose -f docker-compose.yml -f docker-compose.free.yml up -d --build

- Everything (Redis, API, worker, frontend) runs on **one EC2 t3.micro** (1 GB RAM), next to the RDS
  database from `backend/.env`.
- **No sentiment model:** the image is built with `WITH_SENTIMENT=false` and runs with
  `SENTIMENT_ENABLED=false`.
- **Media on the server's disk** (`STORAGE_BACKEND=local`) in a Docker volume `media`, shared by the
  API and the worker, instead of DynamoDB.
- All containers restart on their own after a crash or a reboot (`restart: unless-stopped`).

## Consequences

- Sentiment features (mood charts, sentiment on evidence) are off.
- Media lives on one disk, so back up the `media` volume along with the database.
- The server must get the code from git, plus `backend/.env` copied by hand (it is git-ignored).
- Compose only listens on `127.0.0.1`, so nothing is public by default. The guide recommends an SSH
  tunnel, or Caddy with HTTPS for a public domain. Registration is open, so a public deployment lets
  strangers create accounts.

Step by step: [deploy-free.md](../deploy-free.md).

## Where in the code

`docker-compose.free.yml`, `backend/Dockerfile` (`WITH_SENTIMENT`), `media/storage.py` (`LocalStorage`).
