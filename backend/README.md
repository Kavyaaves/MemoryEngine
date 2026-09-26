# Backend — how it works

A FastAPI app. Every folder has one job, and every module starts with a docstring saying
what it does and where it sits in the flow. This page is the map.

```
app/
├── main.py            creates the FastAPI app (start reading here)
├── config/            settings from environment variables / .env
├── db/                database engine + session
├── models/            database tables: user, source, memory, person, graph, lexicon, usage
├── schemas/           request/response shapes (api.py) and AI output shapes (ai.py)
├── auth/              passwords + login tokens
├── core/              small shared helpers: Redis, rate limiting, time zones
├── api/               HTTP routes — one file per resource, kept thin
│
├── ingestion/         upload → memories
│   ├── dispatch.py        what kind of file is this? → the right parser
│   ├── parsers/           whatsapp.py, instagram.py, documents.py
│   ├── records.py         what parsers return + content hashes
│   ├── pipeline.py        the job: runs every ingestion step in order
│   ├── writer.py          saves memories (skipping ones already stored)
│   ├── graph_builder.py   "who talks to whom" edges
│   └── media.py           photos / audio / video
├── multilingual/      Tamil · Malayalam · Tanglish · English text handling (no AI)
├── people/            name matching (aliases.py) and person records (resolver.py)
├── retrieval/         search — start at hybrid.py
├── agents/            the Ask agent — start at graph.py
├── ai/                OpenAI behind one router, embeddings, prompts, request + token caps
├── media/             where file bytes are stored (a DynamoDB table, or local disk for development)
├── evaluation/        test-set builder, pipeline comparison, answer judge, prompt-cache benchmark
├── observability/     OpenTelemetry tracing
└── workers/           background job queue (arq + Redis)
```

## Follow a request through the code

**1. Uploading a WhatsApp export**

```
POST /api/uploads                          api/uploads.py      validate, store the file, create a job
  → enqueue_ingestion(job)                 workers/queue.py    Redis queue (or run in-process)
  → process_job(job)                       ingestion/pipeline.py
      parse_upload()                       ingestion/dispatch.py → parsers/whatsapp.py
      insert_memories()                    ingestion/writer.py
          content_hashes()   skip what's already stored     ingestion/records.py
          process_text()     normalise + transliterate      multilingual/tanglish.py
          resolver.resolve() author name → Person            people/resolver.py
      build_conversation_edges()           ingestion/graph_builder.py
      embed_memories()                     ai/embeddings.py → ai/providers/router.py → OpenAI
```

**2. Asking "Naan Rahul kooda first enga pona?"**

```
POST /api/ask/stream                       api/ask.py          streams progress to the browser
  → run_agent()                            agents/graph.py     analyze → retrieve → verify → answer
      analyze:  heuristic_analysis()       agents/query_analysis.py   people=[Rahul], order=first
      retrieve: tools.search_memories()    agents/tools.py
                  HybridRetriever.search() retrieval/hybrid.py
                    expand_query()         multilingual/tanglish.py   "naan" → நான், "kooda" → kuda …
                    fts / trgm / vector / graph / temporal paths      retrieval/*.py
                    rrf_fuse() → heuristic_score() → llm_rerank()     retrieval/fusion.py, reranker.py
                    (optional) mmr_order()                            retrieval/diversity.py
                    build_evidence()                                  retrieval/evidence.py
      verify:   enough evidence? else search again
      answer:   router.stream("reasoning", …)   ai/providers/router.py → openai.py (LangChain ChatOpenAI)
                  no AI available? → extractive_answer()              agents/answering.py
```

## Ideas worth understanding

- **Original text is never changed.** Search runs on `search_text`, which combines the
  normalised text, a transliteration, Tanglish variants and phonetic keys
  (`multilingual/tanglish.py`). That's how a Latin-letter query finds Tamil-script messages
  without any AI.
- **Incremental imports.** Every record gets a stable hash (`ingestion/records.py`).
  Re-uploading a chat only stores the new messages.
- **SQL does what SQL is good at.** Counting, date ranges and "first/last" are SQL queries
  (`agents/tools.py`, `retrieval/temporal.py`). The LLM only writes the final answer.
- **Several search paths, then fusion.** Keyword, fuzzy, semantic, graph and temporal
  search each vote, and Reciprocal Rank Fusion combines the votes (`retrieval/fusion.py`).
- **Graceful degradation.** With no API keys, keyword search still works and the agent
  returns the matching memories instead of a written answer (`degraded: true`).
- **Retrieved text is untrusted.** Memories are escaped inside `<memory>` tags and every
  prompt says to never follow instructions found in them (`agents/answering.py`,
  `ai/prompts/`).
- **Uncertain identities are questions, not guesses.** "R" is only merged with "Rahul"
  after the user says yes (`people/`).

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
.venv/Scripts/alembic upgrade head
```

```bash
.venv/Scripts/uvicorn app.main:app --reload
```

```bash
.venv/Scripts/arq app.workers.worker.WorkerSettings
```

```bash
.venv/Scripts/pytest -q
```

Tests need no database, Redis or API keys. `tests/test_sql_compile.py` compiles every
query for PostgreSQL, so broken SQL is caught without a server.

## Changing the schema

`alembic/versions/0001_initial.py` is a frozen SQL snapshot. After editing `models/`,
create a new migration rather than editing 0001:

```bash
.venv/Scripts/alembic revision --autogenerate -m "describe the change"
```

## Measuring quality (evaluation)

All three tools call OpenAI with your key (a full run costs cents) and save a Markdown + JSON report
in `eval/results/`. Run them from `backend/`.

**1. Make a test set** from your own memories: 150 questions in English, Tanglish and search-box
style, each pointing at the memory that answers it. Read `eval/golden.jsonl` afterwards and delete
questions that don't make sense. It quotes your messages, so keep it private.

```bash
.venv/Scripts/python -m app.evaluation.golden_builder --user you@example.com --count 150
```

**2. Compare retrieval pipelines.** Each row adds one step (keyword → vector → hybrid → heuristic
rerank → LLM rerank → MMR), so the table shows what each step is worth. `--answers` also runs the
full agent and has the answer model grade every answer.

```bash
.venv/Scripts/python -m app.evaluation.runner --user you@example.com --dataset eval/golden.jsonl --answers
```

**3. Measure prompt caching**: answer requests with and without a cacheable system prompt.

```bash
.venv/Scripts/python -m app.evaluation.cache_benchmark --rounds 10
```

## Limits and prompt caching

- `MAX_TOKENS_PER_WINDOW` / `TOKEN_WINDOW_HOURS` cap the tokens used per time window (default
  2,000,000 per 24 hours; `ai/usage.py`). The AI Lab shows how much of the window is used.
- OpenAI caches the fixed start of long prompts. `ai/prompts/` keeps system prompts fixed (dates and
  questions go in the user message) and `tests/test_prompts.py` checks the answer prompt stays long
  enough to be cached. Cache hits are saved in `ai_usage.cached_input_tokens`; migration `0002` adds
  that column, so run `alembic upgrade head` after updating.
