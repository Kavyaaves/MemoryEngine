# Personal Multimodal Memory Engine

> Ask your memories or walk through them.

A hosted, multilingual (Tamil / Malayalam / Tanglish / English / code-switched) personal memory engine:
upload WhatsApp, Instagram, journals and documents, then ask questions and get **evidence-grounded,
cited answers**, or explore a 3D timeline. Everything runs in the cloud: AI through hosted APIs
(**OpenAI**, through LangChain), data in **Amazon RDS for PostgreSQL**, and
media files in **Amazon DynamoDB**. There are **no local models**. See [PLAN.md](PLAN.md) for the full
architecture and roadmap and [docs/api-contract.md](docs/api-contract.md) for the HTTP API.

```
React + R3F ──► FastAPI ──► LangGraph agent (analyze → retrieve → verify ⟲ → answer)
                   │               │
                   │               └─► Hybrid retrieval: FTS ∥ pg_trgm ∥ pgvector ∥ graph ∥ temporal
                   │                        → RRF fusion → rerank (heuristic → LLM → MMR) → evidence
                   ├─► Redis/arq ingestion: parse → hash → normalise → resolve people → graph → embed
                   └─► AI Router: OpenAI, retries, request + token caps, prompt caching, graceful degradation
Amazon RDS: Postgres (+pgvector, pg_trgm, full-text) = source of truth · DynamoDB = media files · OpenTelemetry/LangSmith = traces
```

## Cloud setup (OpenAI + AWS)

| Need | Service | Used by |
|---|---|---|
| All tables | Amazon RDS for PostgreSQL (15 or newer) | `app/models/` |
| Semantic search | `vector` extension (pgvector), HNSW index; vectors from OpenAI `text-embedding-3-small` at 768 dimensions | `retrieval/vector.py`, `ai/providers/openai.py` |
| Fuzzy / Tanglish spelling search | `pg_trgm` extension, GIN index | `retrieval/lexical.py` |
| Keyword search | built-in full-text search (`tsvector`) | `retrieval/lexical.py` |
| Answers, transcripts | OpenAI (chat through LangChain's `ChatOpenAI`) | `ai/providers/` |
| Sentiment (positive / negative / neutral) | local Hugging Face model `vishnuexe/TamilSense-model` on CPU — optional `.[sentiment]` extra | `sentiment/`, `api/sentiment.py` |
| Photos (metadata only — never analysed; user captions) | EXIF dates via Pillow (header only), file name, file modified time | `ingestion/photos.py`, `api/photos.py` |
| Photos, audio, video, uploads | a DynamoDB table (files split into 350 KB chunks), shown through signed links | `media/storage.py` |

Setup:

1. **OpenAI:** create a key at <https://platform.openai.com/api-keys> and set `OPENAI_API_KEY`.
   The models used are in `.env.example`; check your key can use them.
2. **Database:** in the RDS console, **Create database** → PostgreSQL, engine version 16 or 17. For development
   from your laptop, choose **Public access: Yes** and allow inbound port 5432 from your IP in the
   database's security group. Copy the **Endpoint** into
   `DATABASE_URL=postgresql://postgres:<password>@<endpoint>:5432/postgres` (URL-encode symbols in the
   password). The app adds the async driver and SSL itself.
3. **Media files:** create an IAM user with DynamoDB access to the table (`CreateTable`, `DescribeTable`,
   `BatchWriteItem`, `Query`) and set `AWS_REGION`, `AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY` and `STORAGE_BACKEND=dynamodb`. Then create the table once, from `backend/`:

   ```bash
   .venv/Scripts/python -m app.media.storage create-table
   ```

4. **Create the tables:** run `.venv/Scripts/alembic upgrade head` from `backend/`. This installs `vector`
   and `pg_trgm`, creates the tables and indexes, and turns on row-level security for every table as a
   safety net (only the table owner — the app — can read rows).

Costs: DynamoDB's always-free tier includes 25 GB of storage. Its free throughput (25 writes per second)
would need about 14 seconds per 350 KB chunk, so the table uses on-demand capacity: roughly $0.65 per GB
uploaded and a few cents per GB viewed. RDS is free for 12 months on AWS accounts that still have the
classic free tier (a `db.t4g.micro` / `db.t3.micro` instance and 20 GB); newer accounts pay with AWS
credits, and afterwards it costs about $15 a month. OpenAI is billed per token; `MAX_DAILY_REQUESTS`
and `MAX_MONTHLY_REQUESTS` cap the number of AI calls, and `MAX_TOKENS_PER_WINDOW` (default 2,000,000)
caps the tokens used every `TOKEN_WINDOW_HOURS` hours (default 24, resetting at midnight UTC; 0 = no cap).
Once a cap is reached the app keeps working without AI (keyword search, answers that list the evidence).

## Quick start (Docker)

```bash
cp .env.example .env
```

Fill in the values above, then:

```bash
docker compose up --build
```

Open <http://localhost:8080>, register, and upload a WhatsApp export (`.txt` or `.zip`). The backend runs
migrations on start. API docs are at <http://localhost:8000/api/docs>.

The backend image includes the local sentiment model (CPU PyTorch + `vishnuexe/TamilSense-model`, downloaded
at build time), so the first build takes a while and the image is about 2.5 GB. Each container that runs the
model uses about 1 GB of RAM, so give Docker at least 4 GB.

## Local development

Backend (Python 3.11+; reads `backend/.env`). No Redis? Leave `REDIS_URL=` empty: uploads are then processed inside the API process, limits are counted per process, and the worker below isn't needed.

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
cd backend && .venv/Scripts/alembic upgrade head && .venv/Scripts/uvicorn app.main:app --reload
```

```bash
cd backend && .venv/Scripts/arq app.workers.worker.WorkerSettings
```

Frontend (Node 20+): see [frontend/README.md](frontend/README.md).

```bash
cd frontend && npm install && npm run dev
```

Tests (no database, Redis, API keys or AWS account needed — OpenAI and DynamoDB are faked):

```bash
cd backend && .venv/Scripts/pytest -q
```

## How the key pieces work

New to the code? Start with the guided tour in [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md).

| Concern | Where | Notes |
|---|---|---|
| Multilingual | `backend/app/multilingual/` | Unicode-block script detection, segment-aware language tags, Tamil/Malayalam → colloquial Latin transliteration, repeat-collapse, phonetic keys, seed Tanglish lexicon plus a personal lexicon learned from your corpus. Each memory's `search_text` bridges scripts, so the query "naan avan kooda pona" matches the stored text "நான் அவன் கூட போனேன்" with no LLM involved. The original text is never modified. |
| Ingestion | `backend/app/ingestion/` | WhatsApp (Android/iOS, 12/24h, dmy/mdy, zip with media), Instagram JSON (mojibake fix), TXT/MD journals split by dated headings, JSON, CSV, PDF, DOCX, EML, and images/audio/video. Per-record content hashes make re-imports **incremental**; whole-file duplicates are detected at upload. |
| Entity resolution | `backend/app/people/` | Names are only auto-merged when they normalise to the same string ("Rahul ❤️" = "rahul"). Weaker matches ("R", "Rahu") become suggestions answered on the People page ("Is R Rahul? Yes/No/Not sure"), and a "yes" merges the two people. |
| Graph | `models`, `retrieval/graph.py` | PERSON–PART_OF→CONVERSATION and PERSON–KNOWS→PERSON edges, plus mention detection. Every edge carries `confidence`, `created_by` and `source_memory_id`. |
| Retrieval | `backend/app/retrieval/` | Five paths fused with weighted RRF, then reranked in up to three stages: a heuristic score, the fast OpenAI model scoring the top 20 passages 0–10 (`RERANKER=llm`, the default), and optional MMR diversity that pushes near-duplicates down (`MMR_LAMBDA`, 1.0 = off). The HNSW vector scan is widened (`ef_search` 200, plus iterative scans on pgvector 0.8+) so filters like "only 2023" don't cut semantic results short, and queries are embedded in the same normalised + transliterated shape as memories. Chronology comes from SQL `ORDER BY timestamp`, never from the LLM. Long documents are chunked with LangChain's `RecursiveCharacterTextSplitter` (1,200 characters, 150 overlap). |
| Agent | `backend/app/agents/` | A LangGraph state machine. SQL tools handle counting, first/last and person resolution. The verify step skips its LLM call when the reranker already scored a passage 8/10 or higher. Every LLM step has a deterministic fallback, so with no AI available you still get an extractive, cited answer flagged `degraded`. |
| Prompt injection | `ai/prompts/`, `agents/answering.py` | Retrieved memories are HTML-escaped inside `<memory>` tags and declared untrusted in every prompt. |
| Quota / routing | `backend/app/ai/` | Task-aware router (every task goes to OpenAI), one retry on transient errors, daily/monthly request caps and a token budget per time window in Redis. Every call is logged to `ai_usage` (including prompt-cache hits), which feeds the AI Lab. |
| Prompt caching | `ai/prompts/`, `ai/providers/openai.py` | Prompts are ordered fixed-first (system prompt → earlier turns → evidence and question), the answer prompt's fixed part is over OpenAI's 1,024-token caching threshold, and each request carries a `prompt_cache_key`. Cached tokens are recorded per call and shown in the AI Lab. |
| Security | `auth/`, `api/uploads.py`, `api/sources.py`, `api/media.py` | JWT auth, per-user scoping on every query, bcrypt, extension allowlist plus magic-number checks, Redis rate limits, signed expiring media links (HMAC, served by the API), row-level security on every table, source-level deletion, and an audit log. |
| Evaluation | `backend/app/evaluation/` | `golden_builder` writes a test set from your own memories; `runner` compares retrieval pipelines (keyword → vector → hybrid → +heuristic → +LLM rerank → +MMR) on hit rate@K, Recall@K, MRR, NDCG and latency, and with `--answers` grades the agent's answers with an LLM judge; `cache_benchmark` measures prompt caching's latency effect. Reports go to `backend/eval/results/`. See [backend/README.md](backend/README.md#measuring-quality-evaluation). |

## Status against PLAN.md §47 (V1 definition of done)

| Item | Status |
|---|---|
| WhatsApp import, text/journal import, incremental ingestion | ✅ built and unit-tested |
| Tamil, Malayalam, Tanglish, English, code-switching, transliteration | ✅ rule-based and unit-tested |
| PostgreSQL, FTS, pg_trgm, vector, hybrid retrieval | ✅ built; SQL compile-tested, **not yet run against the RDS database** |
| OpenAI, LangChain, LangGraph | ✅ router and the full agent graph tested with fakes; the OpenAI provider (LangChain chat + SDK) tested against a fake OpenAI server; **real API calls not yet exercised** |
| Media files in DynamoDB | ✅ chunked storage tested against a fake DynamoDB (moto); **not yet run against AWS** |
| Evidence citations, temporal queries, person resolution, basic graph | ✅ |
| Evaluation (test-set builder, pipeline comparison, answer judge, cache benchmark, RAGAS) | ✅ written and unit-tested; **not yet run against real data** (RAGAS also needs `.[eval]`) |
| React UI (Upload, Ask, Life 3D, People, Media, AI Lab, Settings) | ✅ builds; tested against mocked API responses |

Built beyond V1: a photo library (photos dated from metadata only, user-written captions made searchable
with "Ingest Captions"), audio transcription (OpenAI) on upload, the AI Lab
usage/config and retrieval-comparison views, and OpenTelemetry spans.

**Not built yet** (later phases in PLAN.md): video segmentation (videos are stored but not analysed),
image embeddings / cross-modal similarity, AI occasion/event clustering and place extraction, memory
reconstruction, semantic cache, hierarchical summaries, and the fine-tuning experiments.

## Notes

- `EMBEDDING_DIM` (768) is baked into the migration. OpenAI's `text-embedding-3-small` is asked for exactly
  768 dimensions; changing the size requires a new migration and re-embedding.
- Memories are embedded right after each import. Run `python -m app.ai.embeddings` from `backend/` to embed
  anything missing (e.g. after an outage or a model change); the Redis worker also does this every 30 minutes.
  Memories are keyword-searchable before they are embedded.
- LangSmith tracing turns on when `LANGSMITH_API_KEY` is set (in `.env` or the environment).
