# 0019. Media files in DynamoDB, chunked, served through signed links

- **Status:** Accepted. Supersedes Cloudflare R2 / Supabase Storage (PLAN.md §27).
- **Date:** 2026-09-26

## Context

Photos, audio, video and the uploaded export files must not go into PostgreSQL: large binary data
bloats backups and slows the database. The plan said S3-compatible object storage, but the goal was
to stay within AWS's always-free tier, and DynamoDB's always-free tier includes 25 GB of storage.

## Decision

- File bytes live in one DynamoDB table. PostgreSQL only stores the object **key**.
- DynamoDB refuses items over 400 KB, so files are split into **350 KB chunks**, leaving room for the keys.
- Keys look like `{user_id}/{uploads|photos|audio|video}/{sha256}{.ext}`. Naming a file by its
  content hash means the same file is only stored once.
- The table uses on-demand capacity. The free throughput (25 writes per second) would need about
  14 seconds per chunk.
- A second backend, `LocalStorage`, keeps files in a folder. It is for development and tests, and
  for the free-tier server ([0032](0032-free-tier-deployment.md)). `STORAGE_BACKEND` picks one.
- **Signed links:** the browser can't reach either backend, so the API hands out a link to itself
  (`/api/media/raw`) signed with HMAC that works for 15 minutes.

## Consequences

- Storage is free up to 25 GB. Writes cost about $0.65 per GB uploaded, reads a few cents per GB viewed.
- Every media view goes through the API, which checks the signature and the owner.
- On-demand capacity isn't covered by the free tier, which is why the free-tier deploy uses local disk.

## Where in the code

`backend/app/media/storage.py` (`DynamoDBStorage`, `LocalStorage`, `SignedLinks`), `api/media.py`.
