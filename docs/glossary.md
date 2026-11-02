# Glossary

Terms used in the code and these docs, in plain words. Each one links to where it matters in this app.

## Search and retrieval

**Retrieval.** Finding the memories that might answer a question, before any AI writes an answer.

**RAG (Retrieval-Augmented Generation).** Retrieve relevant text first, then give it to an LLM to
answer from. The answer is grounded in your data instead of the model's general knowledge. The
whole Ask feature is RAG.

**Hybrid retrieval.** Running several kinds of search and merging them, instead of relying on one.
See [0007](decisions/0007-hybrid-retrieval-rrf.md).

**Full-text search (FTS).** PostgreSQL's built-in keyword search. Text is turned into a `tsvector`
(a list of normalised words) and matched against a `tsquery`. Good at exact words, names and numbers.

**pg_trgm (trigram search).** A PostgreSQL extension that splits text into 3-letter pieces
("rahul" → "rah", "ahu", "hul") and compares how many pieces two strings share. It finds misspellings
and Tanglish variants ("seri" vs "sari").

**Embedding.** A list of numbers (here 768) that represents the meaning of a text. Texts with similar
meaning get similar lists, even with no word in common. See [0006](decisions/0006-embeddings-768.md).

**Vector search / semantic search.** Finding the stored embeddings closest to the question's
embedding. "Closest" is usually **cosine similarity**: 1 means the same direction (same meaning),
around 0 means unrelated.

**pgvector.** The PostgreSQL extension that adds a `vector` column type and fast nearest-neighbour search.

**HNSW (Hierarchical Navigable Small World).** The index type pgvector uses to find near vectors
quickly without comparing against every row. It is approximate. `ef_search` sets how hard it looks
(here 200).

**RRF (Reciprocal Rank Fusion).** A way to merge ranked lists using only positions:
`score = Σ weight / (k + rank)`. A memory ranked well by several lists wins.
See [0007](decisions/0007-hybrid-retrieval-rrf.md).

**Reranking.** Re-ordering a candidate list with a more careful (and slower) judgement than the first
search. Here: a heuristic, then an LLM scoring passages 0–10. See [0008](decisions/0008-reranking-stages.md).

**MMR (Maximal Marginal Relevance).** Re-ordering that balances relevance against novelty, so ten
copies of the same forwarded message don't fill the top ten. `MMR_LAMBDA` sets the balance (1.0 = relevance only).

**Graph RAG.** Retrieval that follows relationships (person → conversation → event) as well as text
similarity. Here: the `graph` and `book` search paths.

**Evidence / provenance.** Where an answer came from: source, date, author and the exact snippet.
Every answer shows it.

## Evaluation metrics

**Golden set.** Questions with known correct answers (here: which memory answers each question),
used to measure retrieval. See [0027](decisions/0027-evaluation.md).

**Hit rate@K.** The share of questions where the right memory appears anywhere in the top K results.

**Recall@K.** The share of all correct memories that appear in the top K.

**MRR (Mean Reciprocal Rank).** The average of 1 ÷ (the rank of the first correct result). Rewards
putting the answer at the very top.

**NDCG (Normalised Discounted Cumulative Gain).** Scores the whole ranking: correct results count
for more the higher they appear.

**RAGAS.** A library that scores RAG answers: faithfulness (is it supported by the evidence?),
context precision and context recall.

**LLM judge.** Using a model to grade answers against the expected ones.

## AI and models

**LLM (Large Language Model).** A model that reads and writes text, like GPT-4.1.

**Hosted vs local model.** Hosted models run on the provider's servers and are called over an API.
Local models run on your own machine. See [0001](decisions/0001-hosted-ai-only.md).

**Token.** The unit models read and write: roughly ¾ of an English word. Billing and limits are in
tokens. See [0016](decisions/0016-quota-guard-and-token-budget.md).

**Prompt caching.** The provider reuses the work for a prompt's unchanged beginning, which makes
repeat calls cheaper and faster. See [0017](decisions/0017-prompt-caching.md).

**Structured output.** Asking a model to reply in a fixed JSON shape (a Pydantic model here) instead
of free text, so code can use the result directly.

**Agent.** A program where a model works through steps, using tools (search, SQL) and deciding
whether to continue. Here: the LangGraph Ask agent. See [0003](decisions/0003-langgraph-and-langchain.md).

**State machine (LangGraph).** Steps as nodes, with arrows between them that can loop. For example,
`verify` can go back to `retrieve`.

**Prompt injection.** Text inside the data that tries to give the model instructions ("ignore previous
instructions"). See [0014](decisions/0014-memories-are-untrusted.md).

**Graceful degradation.** Working with fewer features instead of failing when something (here the AI)
is unavailable. See [0015](decisions/0015-graceful-degradation.md).

**Fine-tuning.** Further training an existing model on your own labelled examples so it learns a
specific skill. **Base model**: the starting model. **Derived model**: the result.
See [0024](decisions/0024-one-derived-model.md).

**Teacher model.** A bigger model that labels training examples for a smaller one.

**Baseline.** The simple approach (here usually rules or a word list) that a model has to beat to be worth using.

**BERT / MuRIL.** BERT is a family of models that read text to classify it, rather than generate it.
MuRIL is Google's BERT trained on Indian languages. The sentiment model is built on it.
See [0023](decisions/0023-local-sentiment-model.md).

## Multilingual

**Tanglish.** Tamil written in Latin letters, often mixed with English ("naan office ku poren").

**Code-switching.** Changing language in the middle of a message or sentence.

**Transliteration.** Writing a word in another script by sound (நான் → "naan"). It is not translation:
the meaning isn't changed.

**Unicode normalisation (NFKC).** Turning different byte sequences for the same character into one
form, so equal-looking text compares as equal.

**Phonetic key.** A simplified spelling by sound, so variants like "kooda" and "kuda" share a key.

**Lexicon.** A word list. Here: the seed Tanglish lexicon, the personal lexicon learned from your
messages, and `ADDRESS_TERMS`. See [0010](decisions/0010-multilingual-without-ai.md).

**Address term (vocative).** A word used to address someone: "da", "di", "kutta", a pet name.
See [0025](decisions/0025-address-terms-are-counting.md).

**Mojibake.** Garbled text from reading bytes in the wrong encoding (Instagram exports have it,
and the parser fixes it).

## Backend and infrastructure

**ASGI.** The interface between async Python web apps (FastAPI) and the servers that run them (uvicorn).

**ORM (Object-Relational Mapper).** Python classes that map to database tables (SQLAlchemy models).

**Migration.** A versioned script that changes the database schema (Alembic). Run with `alembic upgrade head`.

**Row-level security (RLS).** A PostgreSQL feature that limits which rows a database user can see.
Here it is a safety net on every table. See [0020](decisions/0020-security-model.md).

**Job queue / worker.** Slow work (imports) is put on a queue, and a separate process (the worker)
picks it up. See [0018](decisions/0018-redis-and-arq-optional.md).

**Incremental ingestion.** Only processing what's new on each import. See [0011](decisions/0011-incremental-ingestion.md).

**Content hash.** A fingerprint of some data (SHA-256): the same data always gives the same hash.

**Chunking.** Splitting long text into overlapping pieces for search. See [0022](decisions/0022-documents-chunking.md).

**JWT (JSON Web Token).** A signed token that proves who you are. The browser sends it with every request.

**bcrypt.** A deliberately slow password hash, so stolen hashes are hard to crack.

**HMAC signature.** A code computed from a secret key and a message. Here it proves a media link was
made by this API and hasn't been changed. See [0019](decisions/0019-media-in-dynamodb.md).

**Magic number.** The first bytes of a file, which reveal its real type whatever its extension says.

**Rate limit.** A cap on requests per user per time window.

**SSE (Server-Sent Events).** One long HTTP response the server keeps writing to, used to stream the
answer as it is written. See [0030](decisions/0030-nginx-same-origin.md).

**OpenTelemetry / span / OTLP.** A standard for tracing. A span is one timed step, and OTLP is the
protocol for sending spans to a collector. See [0028](decisions/0028-observability.md).

**Reverse proxy.** A server (nginx) that receives requests and forwards them to another server (the API).

**Same origin.** The same scheme + host + port. Browsers restrict requests across origins (CORS).

## Docker

**Image / container.** An image is a packaged app with everything it needs. A container is a running copy of it.

**Layer cache.** Each Dockerfile step makes a layer. Docker reuses layers whose inputs didn't change,
so slow steps go first. See [0031](decisions/0031-backend-docker-image.md).

**Build argument (`ARG`).** A value that changes how an image is built, such as `WITH_SENTIMENT=false`.

**Compose override file.** A second Compose file that changes settings of the first, like
`docker-compose.free.yml`. See [0032](decisions/0032-free-tier-deployment.md).

**Volume.** Storage that outlives a container (here: `redisdata`, `media`).

## Frontend

**SPA (Single-Page App).** One HTML page, and JavaScript switches between "pages" without reloading.

**Server state vs client state.** Server state is data from the API, which TanStack Query caches.
Client state is UI-only (theme, login), which Zustand holds. See [0029](decisions/0029-frontend-stack.md).

**Lazy loading.** Downloading a page's code only when it is opened (`React.lazy`).

**WebGL.** The browser API for 3D graphics, which three.js uses.

**React Three Fiber (R3F).** Writing three.js scenes as React components.
