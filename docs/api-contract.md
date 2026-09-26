# API Contract (v1)

Base URL: `/api`. All endpoints except `/auth/register` and `/auth/login` require
`Authorization: Bearer <token>`. All data is scoped to the authenticated user.
Timestamps are ISO-8601 strings (UTC). IDs are UUID strings. `start`/`end` query parameters are
**inclusive** calendar dates (`YYYY-MM-DD`) in the user's timezone. Multipart uploads use repeated `files` parts.
Errors are `{"detail": "..."}`; `503` means the database is unreachable.

## Auth
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/register` | `{email, password, display_name?}` | `{access_token, token_type:"bearer"}` |
| POST | `/auth/login` | `{email, password}` | `{access_token, token_type:"bearer"}` |
| GET | `/auth/me` | – | `User {id, email, display_name, created_at}` |

## Uploads / ingestion
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/uploads` | multipart: `files[]` (1..n), optional `source_type` (`whatsapp`\|`instagram`\|`journal`\|`document`\|`image`\|`audio`\|`video`\|`auto`, default `auto`), optional `self_name` (the user's own name in chats), optional `last_modified[]` (each file's last-modified time in epoch ms, same order as `files`) | `{jobs: Job[]}` |
| GET | `/uploads/jobs` | – | `Job[]` (newest first) |
| GET | `/uploads/jobs/{id}` | – | `Job` |
| POST | `/uploads/jobs/{id}/retry` | – | `Job` |
| GET | `/sources` | – | `Source[]` |
| DELETE | `/sources/{id}` | – | `204` (deletes source + all derived memories) |

```ts
Job = { id, source_id: string|null, filename, source_type, status: "queued"|"processing"|"completed"|"failed"|"duplicate",
        progress: number /*0..1*/, stats: {total?: number, new?: number, skipped?: number, embedded?: number},
        error: string|null, created_at, updated_at }
Source = { id, source_type, name, memory_count, created_at, last_processed_at }
```

## Search
`GET /search?q=&start=&end=&person_id=&source_type=&k=20&mode=hybrid`
(`mode`: `hybrid`|`fts`|`trgm`|`vector`) → `{results: Evidence[], timings_ms: Record<string, number>}`

```ts
Evidence = { memory_id, source_type, source_name, conversation_id: string|null, conversation_title: string|null,
             timestamp: string|null, author: string|null, text, snippet, language, script,
             score: number, retrieval_paths: string[] /* "fts"|"trgm"|"vector"|"graph"|"temporal" */,
             media: {id, kind, url, mime_type}[],
             sentiment: {label: "positive"|"negative"|"neutral", score: number}|null }
```

## Photos
Photos are **never analysed**: an uploaded photo becomes a memory built from its file name and dates only.
Its timeline date is the first one found of: EXIF taken → date in the file name → EXIF changed →
file last-modified (`last_modified` on upload) → upload time. Captions are written by the user and only
become searchable (text, search index, embedding) after `POST /photos/captions/ingest`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/photos?start=&end=&q=&caption=all\|none\|pending\|ingested&limit=200` | – | `{photos: Photo[], pending_captions: number}` (newest first; `q` matches file name or caption) |
| PUT | `/photos/{memory_id}/caption` | `{caption}` | `Photo` (caption saved as a draft → `pending`) |
| POST | `/photos/captions/ingest` | – | `{ingested: number, embedded: number, sentiment: number}` |

```ts
Photo = { memory_id, filename, url, mime_type: string|null, timestamp: string|null,
          date_source: "exif_taken"|"filename"|"exif_changed"|"file_modified"|"uploaded",
          taken_at: string|null, changed_at: string|null, file_modified_at: string|null, uploaded_at,
          caption, caption_status: "none"|"pending"|"ingested" }
```

## Ask (agent)
`POST /ask` body `{question, conversation?: {role:"user"|"assistant", content}[] }`
→ `AskResponse`

`POST /ask/stream` same body → `text/event-stream` with events:
- `event: step` data `{name, detail}` — agent progress (analyze, retrieve, verify, answer)
- `event: evidence` data `Evidence[]`
- `event: token` data `{text}` — answer text chunk
- `event: done` data `AskResponse`
- `event: error` data `{message}`

```ts
AskResponse = { answer: string /* cites evidence as [1], [2] … (1-based index into evidence) */,
                evidence: Evidence[], confidence: "high"|"medium"|"low"|"none",
                analysis: { intent, people: string[], time_start: string|null, time_end: string|null,
                            temporal_order: "first"|"last"|null, modality: string[], rewritten_queries: string[] },
                trace: { steps: {name, latency_ms, detail?}[], provider: string|null, model: string|null, degraded: boolean,
                         finetune: { base_model: string, derived_model: string } | null } }
                # finetune: set when the fine-tuning phase's derived model (backend/app/finetuning/) helped with
                # this answer — base_model is the standard model training started from (e.g. "gpt-4.1-nano-2025-04-14"),
                # derived_model the model trained from it (e.g. "ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123").
                # Evidence found through it has retrieval_paths ["derived"].
```

## Timeline
`GET /timeline?granularity=year|month|day&start=&end=` → `{buckets: {period: string /* "2024" | "2024-06" | "2024-06-14" */, count, sources: Record<string, number>, top_people: string[]}[]}`
`GET /timeline/day/{YYYY-MM-DD}` → `{date, memories: Evidence[]}`

## Sentiment
A local model (`vishnuexe/TamilSense-model`, Tamil + Tanglish) labels each memory positive or negative;
answers below `SENTIMENT_NEUTRAL_BELOW` confidence are `neutral`. New uploads are analysed automatically;
photos only through their ingested caption.

| Method | Path | Response |
|---|---|---|
| GET | `/sentiment/timeline?granularity=year\|month\|day&start=&end=&person_id=` | `{buckets: {period, positive, negative, neutral, mood /* −1..+1 */}[]}` |
| GET | `/sentiment/status` | `{enabled, installed, model, done, remaining, running}` |
| POST | `/sentiment/analyze` | `202` + status (analyses this user's remaining memories in the background) |

## People
| Method | Path | Response |
|---|---|---|
| GET | `/people` | `Person[]` |
| GET | `/people/{id}` | `PersonDetail` |
| GET | `/people/alias-suggestions` | `AliasSuggestion[]` |
| POST | `/people/alias-feedback` body `{alias_id, person_id, answer:"yes"|"no"|"unsure"}` | `{ok:true}` |

```ts
Person = { id, display_name, aliases: string[], memory_count, first_seen: string|null, last_seen: string|null }
PersonDetail = Person & { timeline: {period, count}[], conversations: {id, title, memory_count}[],
                          related_people: {id, display_name, weight}[] }
AliasSuggestion = { alias_id, alias, person_id, person_name, similarity }
```

## AI Lab
`GET /lab/usage` → `{providers: {provider, model, task, request_count, input_tokens, output_tokens, errors, avg_latency_ms, day}[], limits: {max_daily_requests, max_monthly_requests}}`
`GET /lab/config` → `{providers: {name, configured: boolean}[], routing: Record<task, string[]>, embedding_model, embedding_dim, reranker, top_k}`

## Health
`GET /health` → `{status:"ok", db: boolean, redis: boolean}`
