# How the app works: a guided tour

This page explains the whole app in the order you'd meet it as a user: upload a chat, ask a
question, explore the results. Each section ends with the files to read next. Words in *italics*
are explained in the [glossary](glossary.md).

---

## 1. The big picture

Memory Engine turns your exported chats, journals, documents and photos into a searchable personal
history. You can **ask** it questions ("When did I first talk to Rahul about Kerala?") and get answers
with citations, or **walk through** your memories in a 3D world.

```
 Browser (React)
    │  one origin: nginx serves the app and forwards /api
    ▼
 FastAPI (the API) ───────────────► Redis queue ──► Worker (same code, runs imports)
    │                                                   │
    │  Ask: LangGraph agent                              │  Import: parse → store → enrich
    ▼                                                   ▼
 Hybrid retrieval ◄──────────── PostgreSQL on Amazon RDS (source of truth) ──► DynamoDB / disk (file bytes)
    │                              tables + full-text + pg_trgm + pgvector
    ▼
 AI router ──► OpenAI (answers, reranking, embeddings, transcription)
```

Four ideas run through everything:

1. **PostgreSQL is the source of truth.** Every search path, graph and 3D view is built from the
   `memories` table ([0004](decisions/0004-postgres-and-pgvector.md)).
2. **The original text is never changed.** Extra fields are added for search ([0010](decisions/0010-multilingual-without-ai.md)).
3. **AI is a helper, not a requirement.** Every AI step has a fallback ([0015](decisions/0015-graceful-degradation.md)).
4. **Every answer shows its evidence**, and inferred information is labelled as inferred
   ([0013](decisions/0013-graph-with-provenance.md)).

---

## 2. What a memory is

A *memory* is one row in the `memories` table: one WhatsApp message, one journal entry, one chunk of
a PDF, one photo. It is a structured object, not a text blob:

| Field | Example | Why it exists |
|---|---|---|
| `text` | `நான் அவன் கூட போனேன்` | the original, never modified |
| `normalized_text`, `transliteration` | `naan avan kooda ponen` | cleaned-up and Latin-letter versions |
| `language`, `script` | `ta`, `tamil` | `mixed` when one message uses several |
| `search_text` | `நான் அவன் கூட போனேன் naan avan kooda ponen …` | what search runs on: normalised text + transliteration + variants + phonetic keys |
| `search_tsv` | (computed by PostgreSQL) | the full-text index form of `search_text` |
| `timestamp` | `2024-06-14 18:30 +05:30` | chronology is SQL, not AI ([0009](decisions/0009-sql-for-chronology.md)) |
| `author_raw`, `author_person_id` | `Rahul ❤️` → a person | the name as exported, and who it resolved to |
| `content_hash` | `9f2c…` | skips duplicates on re-import ([0011](decisions/0011-incremental-ingestion.md)) |
| `embedding`, `embedding_model` | 768 numbers | semantic search ([0006](decisions/0006-embeddings-768.md)). `NULL` until embedded |
| `meta` | `{"sentiment": …, "address_tags": …, "caption": …}` | extra results that don't need their own column |

The tables around memories:

| Table | Holds |
|---|---|
| `users` | accounts |
| `sources`, `ingestion_jobs`, `conversations` | one row per upload, its import job, and each chat |
| `memory_participants`, `media_assets` | who is in a memory, and the files attached to it |
| `people`, `person_aliases` | people and every name they appear under |
| `relationships` | the graph: generic edges `(type, id) —REL→ (type, id)` with confidence and source |
| `events`, `places` | events (these are the Memory Books) and places |
| `memory_pages`, `memory_page_items`, `universe_changes` | the Memory Universe |
| `lexicon_entries` | the personal Tanglish lexicon |
| `ai_usage`, `audit_log` | every AI call, and sensitive actions |

Read next: `backend/app/models/`.

---

## 3. Following an upload

You drop a WhatsApp export on the Upload page.

```
POST /api/uploads                         api/uploads.py       check type (extension + magic number) and size,
                                                               store the file, create a job
  → enqueue_ingestion(job)                workers/queue.py     Redis queue, or run in-process without Redis
  → process_job(job)                      ingestion/pipeline.py, in the worker
      1. parse                            ingestion/dispatch.py → parsers/whatsapp.py
      2. hash, skip what's already stored ingestion/records.py, writer.py
      3. normalise + transliterate        multilingual/tanglish.py
      4. resolve people                   people/resolver.py   "Rahul ❤️" = "rahul"; "R"? → ask the user
      5. graph edges                      ingestion/graph_builder.py
      6. embed                            ai/embeddings.py → AI router → OpenAI
      7. sentiment                        sentiment/pipeline.py (local model, optional)
      8. update the universe              universe/updater.py
```

What to notice:

- **Step 2 makes imports incremental.** Upload the same chat next month and only the new messages go
  through steps 3–8 ([0011](decisions/0011-incremental-ingestion.md)).
- **Step 3 is pure rules.** That's how a Latin-letter question later finds Tamil-script messages
  without any AI ([0010](decisions/0010-multilingual-without-ai.md)).
- **Step 4 never guesses.** Only identical names merge. Everything else becomes a question on the
  People page ([0012](decisions/0012-entity-resolution-asks.md)).
- **The file bytes** go to DynamoDB (or disk), and PostgreSQL keeps only the key
  ([0019](decisions/0019-media-in-dynamodb.md)).

Read next: `backend/app/ingestion/pipeline.py`, then `ingestion/parsers/whatsapp.py`.

---

## 4. Following a question

You ask *"Naan Rahul kooda first enga pona?"* ("Where did I first go with Rahul?").

```
POST /api/ask/stream                      api/ask.py          streams progress and the answer (SSE)
  → run_agent()                           agents/graph.py     the LangGraph state machine
      analyze   → people=[Rahul], order=first, time window   agents/query_analysis.py
      retrieve  → hybrid search                              retrieval/hybrid.py
      verify    → is the evidence good enough? if not, search again
      answer    → the reasoning model writes a cited answer  agents/answering.py
```

### 4.1 Hybrid retrieval, the heart of the app

```
query ─► expand: Tanglish variants + transliteration     "naan" → நான், "kooda" → kuda …
      ─► six search paths, in parallel:
           fts       exact words          (PostgreSQL full-text)
           trgm      similar spellings    (pg_trgm)
           vector    similar meaning      (pgvector)
           graph     memories with Rahul  (relationships)
           temporal  the right time       (SQL ORDER BY timestamp)
           book      matching events      (Memory Books)
      ─► merge with weighted RRF          retrieval/fusion.py
      ─► rerank: heuristic → LLM → MMR    retrieval/reranker.py, diversity.py
      ─► evidence cards                   retrieval/evidence.py
```

Why so many paths? Each one finds things the others miss, and *RRF* rewards memories that several
paths agree on ([0007](decisions/0007-hybrid-retrieval-rrf.md)). The reranker then reads the best 20
closely ([0008](decisions/0008-reranking-stages.md)).

### 4.2 Things the agent does with SQL, not AI

"First", "last", "how many" and date ranges are SQL queries. The LLM only phrases the result
([0009](decisions/0009-sql-for-chronology.md)). "How do I call Rahul?" is a special case: it counts
address words across the whole chat ([0025](decisions/0025-address-terms-are-counting.md)).

### 4.3 Keeping the answer safe and honest

- Retrieved messages go into the prompt escaped, inside `<memory>` tags marked untrusted
  ([0014](decisions/0014-memories-are-untrusted.md)).
- If the AI is unavailable or over budget, you get the matching memories with citations instead,
  flagged `degraded` ([0015](decisions/0015-graceful-degradation.md), [0016](decisions/0016-quota-guard-and-token-budget.md)).
- The Trace panel shows every step, its latency and the tokens used ([0028](decisions/0028-observability.md)).

Read next: `backend/app/agents/graph.py`, then `retrieval/hybrid.py`.

---

## 5. The pages

| Page | What you do | Backend | Frontend |
|---|---|---|---|
| Upload | import exports, see job progress, delete a source | `api/uploads.py`, `api/sources.py` | `features/upload/` |
| Ask | chat with cited answers, evidence and trace | `api/ask.py`, `agents/` | `features/chat/` |
| Life | a 3D spiral timeline of days and months | `api/timeline.py` | `three/`, `features/timeline/` |
| Memories | the Memory Universe: books along a time river | `api/universe.py`, `universe/` | `universe/`, `features/universe/` |
| People | people, aliases, "Is R Rahul?" questions, mood | `api/people.py`, `people/` | `features/people/` |
| Media | the photo library and captions | `api/photos.py`, `api/media.py` | `features/media/` |
| AI Lab | usage, limits, model routing, retrieval comparison | `api/lab.py`, `ai/usage.py` | `features/lab/` |

The HTTP API is in [api-contract.md](api-contract.md). The frontend's layout rules are in
[frontend/README.md](../frontend/README.md).

---

## 6. The Memory Universe

Memories are grouped into **pages** (a conversation on a day), pages into **books** (an event or
stretch of time), and books float beside a **time river**, one year after another. A book's place
is computed once and never changes, so the world looks the same every time you come back. Each
import only updates the books it touched ([0026](decisions/0026-memory-universe.md)).

Read next: `backend/app/universe/__init__.py` (a map of the folder), then `universe/layout.py`.

---

## 7. Running it

| Setup | Command | Notes |
|---|---|---|
| Local dev | `uvicorn` + `npm run dev` | no Redis needed. See the root [README](../README.md) |
| Docker (full) | `docker compose up --build` | about 4 GB RAM, includes sentiment ([0031](decisions/0031-backend-docker-image.md)) |
| Free tier | `docker compose -f docker-compose.yml -f docker-compose.free.yml up -d --build` | one t3.micro, no sentiment, media on disk ([0032](decisions/0032-free-tier-deployment.md)). Step by step: [deploy-free.md](deploy-free.md) |

In every setup the database is RDS and the AI is OpenAI, both configured in `backend/.env`.

---

## 8. Where to go next

- **Why** each part is built this way: [decisions/](decisions/README.md)
- **What** each package does, and why it's needed: [packages/](packages/README.md)
- **Interview questions** about this project, answered: [faq.md](faq.md)
- **Terms** you don't know: [glossary.md](glossary.md)
- **The original plan** and roadmap: [PLAN.md](../PLAN.md). Its provider and hosting sections are
  out of date. The decisions above say what changed.
