# Interview FAQ

Questions an interviewer is likely to ask about this project, with answers you can give. Each
answer is short enough to say out loud, then points to where the full reasoning lives.

How to use this page:
- **Say the decision, then the reason, then the trade-off.** "I did X because Y. The cost is Z, and
  I'd revisit it if W." Interviewers care most about the trade-off.
- **Use the numbers.** They show you measured, not guessed: 768 dimensions, RRF k = 60, top 20
  reranked, 350 KB chunks, about 10,000 tokens per question.
- **Be honest about what isn't done** ([section 13](#13-limitations-and-what-id-change)). It earns more trust than overselling.

Contents:
1. [The project](#1-the-project) ·
2. [Architecture](#2-architecture) ·
3. [Retrieval and RAG](#3-retrieval-and-rag) ·
4. [The agent and LLMs](#4-the-agent-and-llms) ·
5. [Multilingual text](#5-multilingual-text) ·
6. [Data and ingestion](#6-data-and-ingestion) ·
7. [Database](#7-database) ·
8. [Security and privacy](#8-security-and-privacy) ·
9. [Cost, reliability and scale](#9-cost-reliability-and-scale) ·
10. [Evaluation and fine-tuning](#10-evaluation-and-fine-tuning) ·
11. [Frontend and 3D](#11-frontend-and-3d) ·
12. [Deployment, DevOps and testing](#12-deployment-devops-and-testing) ·
13. [Limitations and what I'd change](#13-limitations-and-what-id-change) ·
14. [Behavioural questions](#14-behavioural-questions)

---

## 1. The project

### Q: Explain the project in 30 seconds.

It's a personal memory engine. You upload your WhatsApp and Instagram exports, journals, documents
and photos, and you can **ask** questions about your past ("When did I first talk to Rahul about
Kerala?") and get cited answers, or **walk through** your memories in a 3D world. What makes it hard
is that the chats mix Tamil, Malayalam, English and Tanglish, so the core of the project is a hybrid
retrieval system that matches across scripts, plus an agent that uses SQL for anything about time or
counts. It's FastAPI, PostgreSQL with pgvector on RDS, LangGraph, OpenAI, and React with React Three Fiber.

### Q: Why build this? Why not just use ChatGPT with a file upload?

Three reasons. **Scale:** a single chat can be 50,000+ messages, far more than fits in a prompt, so
you need retrieval. **Language:** a Latin-letter question has to find Tamil-script messages, and
general tools don't handle Tanglish well. **Trust:** every answer needs to cite the exact message
and date, and questions like "the *first* time" need correct chronology, which an LLM reading a few
passages can't guarantee.

### Q: What are you most proud of?

The hybrid retrieval with cross-script matching. A query like "naan avan kooda pona" finds
"நான் அவன் கூட போனேன்" with **no AI involved**, because each memory stores a `search_text` that
bridges scripts with rules: transliteration, Tanglish variants and phonetic keys. Then six search
paths are fused with RRF and reranked. It's fast, cheap, deterministic and testable.
Deeper: [0010](decisions/0010-multilingual-without-ai.md), [0007](decisions/0007-hybrid-retrieval-rrf.md).

### Q: What was the hardest problem?

Pick one you can talk about in depth:
- **Questions search can't answer.** "How do I call Nihal?" The answer ("da", "kutta") never shares
  a word with the question. In the real data, his name is in 23 of 26,231 messages. I reframed it as
  counting over the whole chat, and then as a fine-tuning task ([0025](decisions/0025-address-terms-are-counting.md)).
- **A 3D layout that never jumps.** Books get a position once, from a fixed date origin and a
  SHA-256 lane, and existing books never move ([0026](decisions/0026-memory-universe.md)).
- **Vector search with filters.** HNSW returns its nearest `ef_search` results and *then* the filter
  applies, so "only 2023" could return almost nothing. I widened `ef_search` to 200 and use
  iterative scans on pgvector 0.8+ ([0004](decisions/0004-postgres-and-pgvector.md)).

---

## 2. Architecture

### Q: Walk me through the architecture.

Browser → nginx (serves the React app and proxies `/api` on the same origin) → FastAPI. Uploads
become jobs on a Redis queue, which an arq worker processes: parse, hash, normalise, resolve people,
build graph edges, embed, sentiment, universe. Questions go to a LangGraph agent: analyse → retrieve
→ verify (and maybe retrieve again) → answer. Retrieval runs six search paths over PostgreSQL. All AI
calls go through one router to OpenAI. PostgreSQL on RDS is the source of truth, and file bytes live
in DynamoDB. Deeper: [architecture.md](architecture.md).

### Q: Why one PostgreSQL instead of a dedicated vector database?

Postgres already does keyword search (FTS), fuzzy search (pg_trgm) and, with pgvector, vector
search, so all of it lives in one database with one backup and one migration history. Semantic
results can be filtered by user and date in the same SQL query. At personal scale (tens or hundreds
of thousands of rows) pgvector's HNSW is plenty. I'd move to Qdrant only if benchmarks showed a need:
much larger scale, complex filters, or a vector workload that should scale separately.
Deeper: [0004](decisions/0004-postgres-and-pgvector.md).

### Q: Why is there a separate worker?

Imports take minutes. The worker means HTTP requests stay fast, an import survives the browser
closing, and big imports don't slow down Ask. The same worker runs scheduled catch-ups: embeddings,
sentiment and universe updates for anything an import missed. Redis is **optional**: without it,
jobs run inside the API process, which keeps local development simple.
Deeper: [0018](decisions/0018-redis-and-arq-optional.md).

### Q: How does the API stream answers?

Server-Sent Events. `POST /api/ask/stream` starts the agent in a background task that pushes events
(`step`, `evidence`, `token`, `done`, `error`) into an `asyncio.Queue`. The response reads from the
queue and writes each event as it arrives, with a keep-alive every 15 seconds. nginx has buffering
turned off for `/api/`, or tokens would arrive in one lump at the end. The background task opens its
own database session, because the request's session closes when streaming starts.
Deeper: [0030](decisions/0030-nginx-same-origin.md).

### Q: Why SSE rather than WebSockets?

The flow is one-way: the client asks once, then the server streams. SSE is plain HTTP, works through
proxies with buffering off, and needs no extra protocol. WebSockets would be worth it for
two-way, real-time interaction, which this app doesn't have.

### Q: How is the code organised?

Each backend folder has one job: `ingestion/`, `multilingual/`, `people/`, `retrieval/`, `agents/`,
`ai/`, `media/`, `universe/`, `evaluation/`, `finetuning/`. Route files in `api/` are kept thin, so
the logic can be tested without HTTP. The frontend has `pages/` (which only arrange components),
`features/` (one folder per area), `hooks/` (every request goes through one), `api/` (one module per
API section) and `stores/`. Deeper: `backend/README.md`, `frontend/README.md`.

---

## 3. Retrieval and RAG

### Q: What is RAG, and how does this app use it?

Retrieval-Augmented Generation: retrieve relevant text first, then have the LLM answer **from** that
text, not from its own memory. Here the retrieval is the hard part: six search paths, fusion,
reranking and evidence cards. The LLM only writes the final answer, and the evidence is shown next
to it with dates and sources.

### Q: Why hybrid search instead of only vector search?

Vector search misses exact things: names, phone numbers, rare slang, and Tanglish words the
embedding model has never seen. Keyword search misses paraphrases. Neither knows *who* is involved or
*when*. So there are six paths: `fts` (exact words), `trgm` (spelling variants), `vector` (meaning),
`graph` (people), `temporal` (time window) and `book` (event-level Graph RAG). Each covers the
others' blind spots. Deeper: [0007](decisions/0007-hybrid-retrieval-rrf.md).

### Q: How do you merge results from paths with incomparable scores?

**Reciprocal Rank Fusion.** It ignores raw scores and uses only rank:
`score = Σ weight(path) / (k + rank)` with `k = 60`. A memory ranked well by several paths beats one
ranked first by only one. The weights are small adjustments: temporal 1.2, fts and vector 1.0, graph
and book 0.8, trgm 0.6. Book is lower than vector because both are semantic, so the agreement bonus
doesn't double-count meaning. Deeper: [0007](decisions/0007-hybrid-retrieval-rrf.md).

### Q: How does the reranker work?

In up to three stages. (1) A **heuristic** score from cheap signals: the RRF score, query-word
coverage, exact phrase, path agreement, similarity, and a penalty for tiny messages like "ok".
(2) An **LLM reranker**: the fast model scores the top 20 passages (500 characters each) from 0 to 10,
and that score then dominates, with the heuristic breaking ties. (3) Optional **MMR** to push
near-duplicates down. If the LLM is unavailable, the heuristic order is kept.
Deeper: [0008](decisions/0008-reranking-stages.md).

### Q: Why an LLM reranker instead of a cross-encoder model?

A cross-encoder would mean running a local model (against [0001](decisions/0001-hosted-ai-only.md))
or paying for another API, and few are trained on Tanglish. The fast OpenAI model already handles a
Tanglish question against a Tamil-script message. It only sees 20 short passages, so the cost is
small. A fine-tuned reranker is on the roadmap, trained from query / positive / negative examples.

### Q: What is MMR, and why is it off by default?

Maximal Marginal Relevance picks results that are relevant **and** different from the ones already
picked, which matters when the same forwarded message appears ten times. It's off by default
(`MMR_LAMBDA = 1.0`) because diversity sometimes costs relevance. The evaluation runner measures it
as its own row, so the setting can be chosen from data. 0.7 is a sensible first value to try.

### Q: How do you choose top-K and the other parameters?

12 results returned, 50 candidates per path, 20 passages reranked, and a similarity cut-off of 0.25.
These are starting points. The evaluation runner ([0027](decisions/0027-evaluation.md)) compares
pipelines on hit rate@K, Recall@K, MRR and NDCG over a golden set built from my own data, and the
values are tuned from that.

### Q: How do you handle "when did I *first*…" questions?

Not with the LLM. The question analyser extracts `order = first` and the people involved, and the
agent calls a SQL tool that sorts by `timestamp`. The LLM only phrases an answer from evidence that
is already in the right order. LLMs are unreliable at sorting dates, and they only see the top few
passages anyway. Deeper: [0009](decisions/0009-sql-for-chronology.md).

### Q: What is Graph RAG here?

Two things. The `graph` path uses explicit edges (person → conversation, person → person) to find
memories involving the people in the question. The `book` path searches **Memory Books**, groups of
related memories with a centroid embedding, so one matching event surfaces its memories even when
each message alone is a weak match. Every edge carries a confidence and a source memory.
Deeper: [0013](decisions/0013-graph-with-provenance.md), [0026](decisions/0026-memory-universe.md).

---

## 4. The agent and LLMs

### Q: Why LangGraph? Isn't an agent overkill?

The flow really is a loop with state: analyse → retrieve → verify → *retrieve again if weak* →
answer, reporting progress as it goes. LangGraph makes those steps explicit nodes that can each be
tested with fake models, and gives tracing for free. It's still a small, deterministic graph, not an
open-ended autonomous agent. I ruled out a second framework like CrewAI on purpose.
Deeper: [0003](decisions/0003-langgraph-and-langchain.md).

### Q: How does the agent decide the evidence is good enough?

The verify step asks the fast model whether the passages answer the question, and if not, retrieval
runs again with an expanded query. It **skips** that LLM call when the reranker already scored a
passage 8/10 or higher, which saves a call on most easy questions.

### Q: Which models do you use, and why?

`gpt-4.1-mini` writes answers. `gpt-4.1-nano` handles quick jobs: question analysis, reranking,
verification. `text-embedding-3-small` at 768 dimensions makes embeddings, and
`gpt-4o-mini-transcribe` handles audio. Small models do the many cheap calls, and the stronger model
only writes the final answer. All are configurable, because OpenAI retires models.
Deeper: [0002](decisions/0002-openai-behind-a-router.md).

### Q: Why OpenAI only? Isn't that vendor lock-in?

It was a pragmatic switch from Gemini + Groq: one key, one bill, and one embedding space (vectors
from different models can't be compared). Lock-in is limited by design: everything goes through an
`AIRouter` that takes a **list** of providers per task. Adding a fallback means writing one provider
class and editing a routing table, with no changes for callers. The real lock-in is the embeddings,
since changing models means re-embedding.

### Q: What happens when OpenAI is down or the budget runs out?

The app degrades instead of failing. The router raises `AIUnavailable`, and every AI step has a
rule-based fallback: heuristic question analysis, keyword/fuzzy/graph/temporal search, heuristic
ranking, and an **extractive answer** that lists the matching memories with citations, flagged
`degraded`. Deeper: [0015](decisions/0015-graceful-degradation.md).

### Q: How do you prevent hallucination?

- The answer prompt only contains retrieved evidence, and says to answer only from it.
- Every answer shows its evidence with sources and dates, so a claim can be checked.
- Counting and chronology come from SQL, not the model.
- Answers separate FACT, AI-INFERRED and UNCERTAIN, and AI-made groupings keep their supporting memories.
- The evaluation runner's LLM judge (and RAGAS faithfulness) measures it.

It reduces hallucination. It doesn't make it impossible.

### Q: How do you handle prompt injection?

The retrieved memories include other people's messages, so they're untrusted. They're HTML-escaped
inside `<memory>` tags, and every system prompt says text inside those tags is evidence, never
instructions. Escaping means a message can't close the tag or start a new role. It lowers the risk
but doesn't eliminate it, and prompt-injection tests are on the roadmap.
Deeper: [0014](decisions/0014-memories-are-untrusted.md).

### Q: What is prompt caching, and how did you use it?

OpenAI reuses the work for a prompt's unchanged beginning (from 1,024 tokens). I order prompts
fixed-first (system → earlier turns → evidence and question), keep anything that changes out of the
system prompt, keep the answer prompt's fixed part above 1,024 tokens (a test checks this), and send
a `prompt_cache_key`. Cached tokens are recorded per call, and a benchmark measures the latency effect.
Deeper: [0017](decisions/0017-prompt-caching.md).

### Q: Why not run a local LLM to save money and protect privacy?

The target is a 1 GB server with no GPU. A useful local LLM needs far more, and it would tie the app
to GPU hosting. So the rule is hosted AI only, and the most private parts don't use AI at all:
search, multilingual matching and photos. The one local model, sentiment, is a small CPU classifier,
not an LLM. Deeper: [0001](decisions/0001-hosted-ai-only.md).

---

## 5. Multilingual text

### Q: How does a Latin-letter query find Tamil-script text?

Each memory stores its original `text`, plus a `search_text` that combines the normalised text, a
transliteration (Tamil/Malayalam → colloquial Latin), Tanglish variants and phonetic keys. Queries go
through the same expansion (`expand_query`), so both sides meet in the same shape. For example,
`naan avan kooda pona` expands to `naan, avan, kooda, pona, நான், nan, அவன், கூட, kuda, போன`. It's all
rules: deterministic, free, and unit-tested. Deeper: [0010](decisions/0010-multilingual-without-ai.md).

### Q: Why not translate everything to English?

Translation is lossy and expensive at 50,000+ messages, and it's wrong for search. A question in
Tanglish should match the user's own words, slang and nicknames exactly. The original text is never
modified, and meaning-level cross-language matching is left to vector search and the LLM reranker.

### Q: How do you handle spelling variation like "seri / serii / sari / சரி"?

At several levels. Repeated letters are collapsed ("seriii" → "seri"), phonetic keys group sound-alike
spellings, a seed Tanglish lexicon maps variants to a canonical form, and a **personal lexicon** is
learned from the user's own messages. pg_trgm then catches whatever is left.

### Q: How do you detect the language of a message?

By Unicode block for the script (Tamil, Malayalam, Latin), then rules for Latin-script text
(English vs Tanglish vs Manglish). It's **segment-aware**: one message can be tagged with several
languages, because code-switching mid-sentence is normal in this data.

---

## 6. Data and ingestion

### Q: How do you avoid duplicates when someone re-uploads the same chat?

Every record gets a stable SHA-256 **content hash** of the source fingerprint, timestamp, author and
text. A unique constraint on `(user_id, content_hash)` enforces it, and the writer skips hashes it
already has. Two genuinely identical messages ("ok" twice in one minute) get a counter, so both are
kept. Re-uploading a 54,000-message chat to add a week only processes that week.
Deeper: [0011](decisions/0011-incremental-ingestion.md).

### Q: How do you parse so many formats?

One parser per source, all returning the same record shape, so everything after parsing is shared.
WhatsApp handles Android and iOS, 12- and 24-hour clocks, day-first and month-first dates, and zips
with media. Instagram JSON needs a mojibake fix. Journals are split by dated headings, and
PDF/DOCX are chunked at 1,200 characters with 150 of overlap. `dispatch.py` detects the type.
Deeper: [0022](decisions/0022-documents-chunking.md).

### Q: How do you know two names are the same person?

Names are normalised (NFKC, lower-case, emoji dropped, every script kept), and only **identical**
normalised names merge automatically: "Rahul ❤️" = "rahul". Weaker matches become a question on the
People page, "Is R Rahul? Yes / No / Not sure". "r" vs "rahul" scores 0.75 and "rahu" vs "rahul" scores
0.85, both above the 0.72 suggestion threshold. A wrong merge corrupts every answer about both
people, so the system asks rather than guesses. Deeper: [0012](decisions/0012-entity-resolution-asks.md).

### Q: Why don't you analyse photos with a vision model?

Privacy, cost and accuracy. Photos are the most private data, a vision call per photo is expensive
for a large library, and a model's caption ("two people at a table") misses what matters ("Amma's
60th"). So photos use **metadata only**: the EXIF date taken (read from the header, pixels never
decoded), the file name and the modified time. The user writes captions, which become searchable
when they choose to ingest them. Deeper: [0021](decisions/0021-photos-metadata-only.md).

### Q: How does sentiment work, and why is it local?

A small local classifier, TamilSense (MuRIL fine-tuned on Tamil and Tanglish), running on the CPU.
One LLM call per message would be expensive at 50,000+ messages, and this model knows Tanglish. It
only outputs positive or negative, so confidence below 0.75 is labelled neutral ("ok da"). Results go
in `meta`, so no schema change was needed. It costs about 1 GB of RAM, which is why the free-tier
deploy turns it off. Deeper: [0023](decisions/0023-local-sentiment-model.md).

---

## 7. Database

### Q: Explain your vector index.

pgvector's **HNSW** index on `vector(768)` with cosine distance (`m = 16`, `ef_construction = 64`).
HNSW is a layered graph of nearest neighbours. Search starts at the top layer and walks down,
visiting a small fraction of the rows. It's approximate: faster, but it can miss a true neighbour.
`ef_search` (set to 200 here) trades speed for recall.

### Q: Why 768 dimensions instead of the model's 1,536?

`text-embedding-3-small` supports shortened embeddings with only a small quality loss, and 768 halves
the storage and index size and speeds up search. The size is fixed in the migration, so changing it
means a new migration and re-embedding. Deeper: [0006](decisions/0006-embeddings-768.md).

### Q: How do you do full-text search on Tamil? Postgres has no Tamil dictionary.

The `search_tsv` column uses the `simple` configuration (no stemming), computed by PostgreSQL itself
from `search_text`. Because `search_text` already contains the transliteration and variants, the
multilingual work happens before Postgres sees the text, and `simple` is enough.

### Q: How do you manage schema changes?

With Alembic migrations, applied automatically on container start (`alembic upgrade head`).
`0001` is a frozen SQL snapshot (extensions, tables, indexes, row-level security), and later changes
are new revisions (`0002` cached tokens, `0003` the Memory Universe). Applied migrations are never
edited. `0003` only **adds** derived tables, so it can't damage existing data.

### Q: How do you test SQL without a database?

`tests/test_sql_compile.py` compiles every query with SQLAlchemy's PostgreSQL dialect. Broken SQL,
wrong columns and dialect mistakes fail the test suite with no database running.

---

## 8. Security and privacy

### Q: This holds very private data. How is it protected?

In layers ([0020](decisions/0020-security-model.md)):
- JWT auth, and bcrypt for passwords.
- **Every query filters by `user_id`.** Every user-owned table has it, deleted with the user.
- **Row-level security** on every table, as a safety net.
- **API keys only on the server.** The browser never talks to OpenAI.
- Uploads are checked by extension **and** magic number, with size limits.
- Rate limits per user.
- **Signed, expiring media links** (HMAC, 15 minutes).
- Source-level deletion, and an audit log.
- In production the app refuses to start with the default `SECRET_KEY`.

### Q: How do media files get to the browser if storage isn't public?

The API hands out a link to itself, `/api/media/raw?...`, signed with an HMAC of the key and the
expiry. It works for 15 minutes. The API checks the signature, then streams the bytes. Storage is
never exposed, and links can't be forged or reused later. Deeper: [0019](decisions/0019-media-in-dynamodb.md).

### Q: What are JWT's downsides here?

A JWT can't be revoked before it expires (7 days here). Logging out only clears it in the browser.
Changing `SECRET_KEY` invalidates everyone. For a single-user personal app that's acceptable. For a
multi-user product I'd add short-lived access tokens with refresh tokens, or a revocation list.

### Q: What data leaves your server?

Only the text sent to OpenAI for AI features: the question, retrieved passages for reranking and
answering, and text to embed. Photos never leave, and neither does sentiment (local), keyword search
or multilingual matching. The AI Lab shows every AI call that was made.

---

## 9. Cost, reliability and scale

### Q: How do you control OpenAI costs?

A quota guard checks, before every call, daily and monthly request caps and a **token budget per
time window** (default 2,000,000 tokens per 24 hours, about 200 questions at roughly 10,000 tokens
each). Every call is logged to `ai_usage`, including prompt-cache hits, and shown in the AI Lab. When
a limit is hit, the app degrades instead of spending. Small models do most calls, the verify step is
skipped when evidence is clearly strong, and prompts are structured for caching.
Deeper: [0016](decisions/0016-quota-guard-and-token-budget.md).

### Q: What does it cost to run?

The free-tier deployment is one EC2 t3.micro, RDS on the 12-month free tier, and media on the
server's disk, so OpenAI is the only cost ([0032](decisions/0032-free-tier-deployment.md)). With
DynamoDB, storage is free up to 25 GB, and on-demand writes cost about $0.65 per GB uploaded.

### Q: What happens if Redis goes down?

The app keeps working. After one failed call, Redis is skipped for a while (instead of every call
waiting about 2 seconds for its own timeout), jobs run inside the API, and limits are counted per
process. Deeper: [0018](decisions/0018-redis-and-arq-optional.md).

### Q: How would this scale to many users or much more data?

- **API:** stateless, so add containers behind the proxy. Watch RDS connections: the pools are
  5 + 5 per process, and a small RDS allows about 80.
- **Imports:** add workers. arq jobs are independent, with up to 4 per worker.
- **Vectors:** HNSW is fine to millions of rows. Beyond that, or with heavy filters, benchmark Qdrant.
- **Universe:** already incremental. Only touched books are recounted, in 1,500-page transactions.
- **Costs:** the per-user token budget becomes essential, and a semantic cache (planned) would help.

### Q: How do you know what's slow?

Every answer carries a trace of its steps, with latency, candidates per path, models and tokens, and
the Ask page shows it. OpenTelemetry spans (per AI call and per HTTP request) go to any OTLP
collector when configured, and LangSmith traces the LangChain/LangGraph runs. One `StepTimer` feeds
both the visible trace and the spans. Deeper: [0028](decisions/0028-observability.md).

---

## 10. Evaluation and fine-tuning

### Q: How do you evaluate retrieval quality?

On my own data, because no public benchmark has Tanglish WhatsApp chats. `golden_builder` writes
about 150 questions from real memories (English, Tanglish, search-box style), each pointing at the
memory that answers it, and I prune the bad ones. `runner` compares pipelines where each row adds one
step (keyword → vector → hybrid → heuristic → LLM rerank → MMR) on hit rate@K, Recall@K, MRR, NDCG
and latency. `--answers` adds an LLM judge, and RAGAS is optional.
Deeper: [0027](decisions/0027-evaluation.md).

### Q: Explain MRR and NDCG.

**MRR**: for each question take 1 ÷ (the rank of the first correct result), then average. 1.0 means
the answer is always first. **NDCG** scores the whole ranking, with correct results counting for less
the lower they appear, normalised against the perfect order. MRR suits "one right answer", and NDCG
suits several relevant results. **Recall@K** asks whether the right memories are in the top K at all.

### Q: What did you fine-tune, and why that?

An **address-term tagger**: for each message, which words address the other person ("da", "kutta",
pet names). The word-list baseline can't tell "panni" the pet name from "panni vechen" ("did it"), or
"da" as address from "da" as a sentence ending. A small classifier that reads the whole message can.
It's measured against the baseline on held-out examples. Deeper: [0025](decisions/0025-address-terms-are-counting.md).

### Q: How is fine-tuning organised?

One **derived model**. Each training run starts from the current derived model (not the base) and
includes every task's data, so a new skill doesn't erase an old one. Labels come from a bigger teacher
model (`gpt-4.1`), and user corrections become the gold set. The model runs at **import time**, never
per question, and nothing depends on it: without it, every task uses its baseline. Answers that used
it are badged. Deeper: [0024](decisions/0024-one-derived-model.md).

---

## 11. Frontend and 3D

### Q: Walk me through the frontend stack.

React 19 + TypeScript on Vite. **TanStack Query** for server state, with every request in a `use*`
hook and keys centralised so one call refreshes everything after an import. **Zustand** for client
state: auth (persisted and synced across tabs), theme, the chat stream, and universe navigation.
Tailwind v4 with shadcn-style components the repo owns. React Three Fiber + drei for 3D, lazy-loaded.
Deeper: [0029](decisions/0029-frontend-stack.md), [packages/frontend.md](packages/frontend.md).

### Q: Why both TanStack Query and Zustand?

They solve different problems. Server state needs caching, refetching, de-duplication and
invalidation, which TanStack Query does. Client state is small and synchronous, which Zustand does
with almost no code. Putting server data in Zustand means rebuilding a cache by hand, and putting UI
state in TanStack Query doesn't fit its model.

### Q: How do you keep one user's data from showing for another after logout?

The query client subscribes to the auth store and **clears the entire cache** whenever the token
changes: logout, a 401, or another tab signing in as someone else. The chat store clears the
conversation the same way.

### Q: How do you keep the 3D pages fast?

Lazy-loading: three.js is only downloaded when you open Life or Memories. Labels are rationed (at
most 10–18, only near where you're looking, recomputed every 300 ms rather than every frame). WebGL is
checked first, and an error boundary falls back to a list view if the 3D view fails.

### Q: How did you make the 3D layout stable?

Positions are computed once, when a book is created, and stored. The x axis is days since a **fixed**
origin (1 Jan 2000), so older imports extend to the left without shifting anything. A book's angle is
its lane (a person or conversation), from a SHA-256 hash, because Python's `hash()` changes between
runs. A new book that would overlap moves itself, and existing books never move.
Deeper: [0026](decisions/0026-memory-universe.md).

---

## 12. Deployment, DevOps and testing

### Q: How is it deployed?

Docker Compose: Redis, the API, the worker (the same image with a different command) and the
frontend (nginx). The database is RDS, configured in `backend/.env`. Migrations run when the API
container starts. For the free tier, an override file runs everything on one t3.micro, with no
sentiment model and media on a disk volume. Compose binds only to `127.0.0.1`, so by default the app
is reached through an SSH tunnel, or through Caddy with automatic HTTPS for a public domain.
Deeper: [0031](decisions/0031-backend-docker-image.md), [0032](decisions/0032-free-tier-deployment.md),
[deploy-free.md](deploy-free.md).

### Q: What did you do to make the Docker image good?

- **Layer order** from slowest-changing to fastest: user → CPU-only torch → model download →
  `requirements.txt` → code. A code change rebuilds in seconds.
- **CPU-only PyTorch** saves about 2 GB of GPU libraries.
- **The model is baked in** at build time, so containers start ready, with no Hugging Face at runtime.
- **A non-root user**, created *before* the model download so no `chown -R` duplicates the 1 GB layer.
- **A `WITH_SENTIMENT` build argument**: about 500 MB without the model, instead of about 2.5 GB.
- `.dockerignore` keeps `.env`, keys and private eval data out of the build.

### Q: How do you test without a database, Redis or API keys?

- Fakes at the boundaries: OpenAI through `httpx.MockTransport`, DynamoDB through `moto`, and fake
  chat models for the agent graph.
- Pure functions for the hard logic (parsers, multilingual rules, fusion, layout, aliases), tested directly.
- SQL compiled for PostgreSQL without a server.
- Redis-optional paths tested explicitly.

`pytest -q` runs everything offline.

### Q: What's your CI/CD?

There's no CI pipeline in the repo yet. Tests, the type check (`npm run typecheck`) and `ruff` are
run locally. The next step is a GitHub Actions workflow running `pytest`, `ruff check`,
`npm run build` and a Docker build on every PR, then deploying on merge.

---

## 13. Limitations and what I'd change

### Q: What isn't finished?

Be upfront (from `README.md`):
- The retrieval SQL is compile-tested but **hasn't run against the real RDS database**. The OpenAI
  provider and DynamoDB storage are tested against fakes, not the real services.
- The evaluation tools are written and unit-tested but **haven't been run on real data**.
- **Not built:** video analysis, image embeddings / cross-modal search, AI event and place
  extraction, memory reconstruction, the semantic cache, and hierarchical summaries.
- There's no CI pipeline.
- Registration is open to anyone who can reach the site. That's fine behind an SSH tunnel, but a
  public deployment needs it locked down ([deploy-free.md](deploy-free.md#option-b-your-own-domain-with-https)).

### Q: What would you do differently?

Answer honestly. Good options:
- **Run the evaluation earlier.** The weights and thresholds are reasonable defaults, but they should be measured.
- **Real-service integration tests** (a disposable Postgres with pgvector, LocalStack), alongside the fakes.
- **One source for Python dependencies.** `requirements.txt` duplicates `pyproject.toml`. A lock file
  (`uv lock` or `pip-compile`) would pin exact versions and remove the drift.
- **Refresh tokens** instead of 7-day JWTs, if it ever had more than one user.
- **Add the provider fallback** the router was designed for, so an OpenAI outage doesn't drop AI entirely.

### Q: What's the biggest risk in the design?

**Embedding lock-in.** Every vector comes from one OpenAI model at a fixed size, so changing the
model means re-embedding everything, and costs scale with the data. Second: **missing `user_id`
filters** in new queries. Row-level security is the safety net, but the convention has to be kept.

---

## 14. Behavioural questions

Use real moments from building this. Each prompt below links to the decision record that tells the story.

| Question | A story from this project |
|---|---|
| "Tell me about a time you changed direction." | Switching from Gemini + Groq to OpenAI only, and Supabase to AWS ([0002](decisions/0002-openai-behind-a-router.md), [0005](decisions/0005-amazon-rds.md)) |
| "A time you chose not to use AI." | Photos metadata-only ([0021](decisions/0021-photos-metadata-only.md)), and rules for multilingual matching ([0010](decisions/0010-multilingual-without-ai.md)) |
| "A time you reframed a problem." | "How do I call X?" is counting, not search ([0025](decisions/0025-address-terms-are-counting.md)) |
| "How do you make decisions under uncertainty?" | People are only merged when certain, and otherwise the user is asked ([0012](decisions/0012-entity-resolution-asks.md)) |
| "How do you design for failure?" | Every AI step has a fallback ([0015](decisions/0015-graceful-degradation.md)), and Redis is optional ([0018](decisions/0018-redis-and-arq-optional.md)) |
| "How do you balance cost and quality?" | Small models for quick jobs, the token budget, skipping verify on strong evidence, prompt caching ([0016](decisions/0016-quota-guard-and-token-budget.md), [0017](decisions/0017-prompt-caching.md)) |
| "How do you know your work is good?" | Pipeline comparison on a golden set from real data ([0027](decisions/0027-evaluation.md)) |
| "Working within tight constraints." | Fitting the app on a 1 GB free-tier server ([0032](decisions/0032-free-tier-deployment.md)) |

Structure each one as **Situation → what I decided and why → the trade-off → the result, or what I'd measure next.**
