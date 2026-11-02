# 0005. Host the database on Amazon RDS for PostgreSQL

- **Status:** Accepted. Supersedes Supabase.
- **Date:** 2026-09-26

## Context

The database first lived on Supabase. When media moved to AWS ([0019](0019-media-in-dynamodb.md)),
keeping the database on a different cloud meant two accounts, two regions and cross-cloud latency.

## Decision

- Use Amazon RDS for PostgreSQL 15 or newer, in `ap-south-1` (Mumbai), the same region as the media table.
- The schema is unchanged (pgvector, pg_trgm, full-text search). The migrations install the extensions.
- `DATABASE_URL` is accepted exactly as the RDS console shows it. The app adds the async driver
  (`+asyncpg`) and `ssl=require` for `*.rds.amazonaws.com` hosts, because RDS 15+ only accepts
  encrypted connections.
- Connection pools stay small (5 + 5 overflow per process), because a small RDS instance allows only
  about 80 connections in total.

## Consequences

- RDS is free for 12 months on accounts with the classic free tier (`db.t4g.micro` / `db.t3.micro`,
  20 GB), then about $15 a month.
- For development from a laptop the instance needs public access and an inbound rule for port 5432.

## Where in the code

`backend/app/config/settings.py` (`to_async_database_url`, `db_pool_size`), `app/db/session.py`.
