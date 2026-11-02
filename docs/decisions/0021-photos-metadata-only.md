# 0021. Photos: metadata only, captions written by the user

- **Status:** Accepted. Replaces the vision pipeline in PLAN.md §17.

## Context

The plan was to send every photo to a vision model for captions, people and objects. Photos are the
most private part of the data, a vision call per photo is expensive for a large library, and a
model's caption of a personal photo is often wrong about what matters ("two people at a table" vs
"Amma's 60th birthday").

## Decision

- **Pixels are never decoded and photos are never sent to an AI model.**
- A photo becomes one memory, built only from its file name, the EXIF "taken" date (read from the
  file header), the EXIF "changed" date and the file's last-modified time.
- The date comes from the best source available, in order: EXIF taken → date in the file name →
  EXIF changed → file modified → upload time. So every photo gets a place on the timeline.
- The user can write a caption on the Media page. It stays a draft until "Ingest Captions", which
  makes it the memory's searchable text (normalised, embedded and analysed for sentiment).

## Consequences

- No AI cost per photo, and no photo leaves the server.
- Photos are only searchable by date and by the captions the user writes. Image similarity and
  cross-modal search are not built.
- There is no `vision` task in the AI router and no `OPENAI_VISION_MODEL` setting. The unused
  vision code (the provider method, its prompt and its output schema) was removed on 2026-11-02.
  An old `.env` that still sets `OPENAI_VISION_MODEL` is harmless, because unknown settings are ignored.

## Where in the code

`backend/app/ingestion/photos.py`, `api/photos.py`, `frontend/src/features/media/PhotoLibrary.tsx`.
