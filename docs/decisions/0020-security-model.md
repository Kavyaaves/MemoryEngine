# 0020. Security: per-user scoping, keys on the server, defence in depth

- **Status:** Accepted

## Context

The database holds someone's private conversations, so a data leak is the worst failure this app
can have. A single protection can fail; several layers make that much less likely to matter.

## Decision

| Layer | What it does |
|---|---|
| Login | JWT bearer tokens (HS256, 7-day lifetime), passwords hashed with bcrypt |
| Per-user scoping | every user-owned row has `user_id` (deleted with the user), and every query filters on it |
| Row-level security | turned on for every table as a safety net: only the table owner (the app) can read rows |
| API keys | live only on the server (`settings.py`). The browser never talks to OpenAI |
| Uploads | extension allowlist plus magic-number checks (the file's real type), size limits |
| Rate limits | per user, per endpoint, in Redis |
| Media | signed, expiring links ([0019](0019-media-in-dynamodb.md)) |
| Deletion | a whole source can be deleted with everything derived from it |
| Audit | an audit log of sensitive actions |

## Consequences

- Change `SECRET_KEY` from its default in production. It signs both login tokens and media links.
- Forgetting the `user_id` filter in a new query is the main risk, so keep query code in the
  retrieval and tools modules, where the pattern is established.

## Where in the code

`backend/app/auth/security.py`, `models/columns.py` (`user_fk`), `api/uploads.py`, `api/sources.py`,
`api/media.py`, `core/ratelimit.py`, `alembic/versions/0001_initial.py`. PLAN.md §39 and §41.
