# Decision records

Every significant choice in the app, one file each: the problem, what was decided, what it costs,
and where it is in the code. These are **Architecture Decision Records** (ADRs): short notes written
so that someone joining later, or you in six months, can see *why* things are the way they are.

## How to read one

Every record has the same four parts:

| Part | Answers |
|---|---|
| **Context** | What problem forced a choice? What was true at the time? |
| **Decision** | What we chose, specifically, with the numbers |
| **Consequences** | What it costs, what it makes easy, and what to watch out for |
| **Where in the code** | The files to open next |

**Status** is *Accepted* (in force) or *Superseded* (replaced by a later record, which it links to).

## All decisions, by topic

### Foundations

| # | Decision |
|---|---|
| [0001](0001-hosted-ai-only.md) | Hosted AI only, no local LLMs |
| [0002](0002-openai-behind-a-router.md) | OpenAI for every AI task, behind one router |
| [0003](0003-langgraph-and-langchain.md) | LangGraph runs the Ask agent, LangChain talks to the models |
| [0004](0004-postgres-and-pgvector.md) | PostgreSQL is the single source of truth, with pgvector for vectors |
| [0005](0005-amazon-rds.md) | Host the database on Amazon RDS for PostgreSQL |

### Search and answers

| # | Decision |
|---|---|
| [0006](0006-embeddings-768.md) | Embeddings: text-embedding-3-small at 768 dimensions |
| [0007](0007-hybrid-retrieval-rrf.md) | Hybrid retrieval: several search paths merged with weighted RRF |
| [0008](0008-reranking-stages.md) | Rerank in stages: heuristic, then LLM, then optional MMR |
| [0009](0009-sql-for-chronology.md) | SQL does counting and chronology, never the LLM |
| [0025](0025-address-terms-are-counting.md) | "How do I call X?" is a counting task, not a search |

### Text and data

| # | Decision |
|---|---|
| [0010](0010-multilingual-without-ai.md) | Keep the original text; bridge scripts with rules, not AI |
| [0011](0011-incremental-ingestion.md) | Incremental ingestion with content hashes |
| [0012](0012-entity-resolution-asks.md) | People are only merged automatically when the names are identical |
| [0013](0013-graph-with-provenance.md) | Graph edges carry their evidence; inferred is never shown as fact |
| [0021](0021-photos-metadata-only.md) | Photos: metadata only, captions written by the user |
| [0022](0022-documents-chunking.md) | Parsers per source; long documents split into 1,200-character chunks |
| [0026](0026-memory-universe.md) | The Memory Universe: derived, stable, and updated incrementally |

### Safety, cost and reliability

| # | Decision |
|---|---|
| [0014](0014-memories-are-untrusted.md) | Retrieved memories are untrusted data, never instructions |
| [0015](0015-graceful-degradation.md) | Every AI step has a fallback that needs no AI |
| [0016](0016-quota-guard-and-token-budget.md) | A quota guard: request caps, a token budget, and a usage log |
| [0017](0017-prompt-caching.md) | Order prompts fixed-first so OpenAI can cache them |
| [0020](0020-security-model.md) | Security: per-user scoping, keys on the server, defence in depth |

### Models we run or train

| # | Decision |
|---|---|
| [0023](0023-local-sentiment-model.md) | Sentiment from a small local model: TamilSense on the CPU |
| [0024](0024-one-derived-model.md) | Fine-tuning: one derived model, trained task by task, always optional |

### Measuring

| # | Decision |
|---|---|
| [0027](0027-evaluation.md) | Measure retrieval on your own data, one step at a time |
| [0028](0028-observability.md) | Observability: a trace in every answer, OpenTelemetry and LangSmith opt-in |

### Infrastructure and frontend

| # | Decision |
|---|---|
| [0018](0018-redis-and-arq-optional.md) | Background jobs with Redis + arq, and Redis is optional |
| [0019](0019-media-in-dynamodb.md) | Media files in DynamoDB, chunked, served through signed links |
| [0029](0029-frontend-stack.md) | Frontend: React + Vite, TanStack Query for server data, Zustand for the rest |
| [0030](0030-nginx-same-origin.md) | nginx serves the frontend and proxies /api on the same origin |
| [0031](0031-backend-docker-image.md) | One backend image for the API and the worker, layered for fast rebuilds |
| [0032](0032-free-tier-deployment.md) | A free-tier deployment on one t3.micro |

## Where PLAN.md is out of date

[PLAN.md](../../PLAN.md) is the original design. These sections were later replaced:

| PLAN.md says | Now | Record |
|---|---|---|
| Gemini primary, Groq fallback (§2, §22) | OpenAI for everything | [0002](0002-openai-behind-a-router.md) |
| Supabase database | Amazon RDS | [0005](0005-amazon-rds.md) |
| Cloudflare R2 / S3 for media (§27) | DynamoDB, or local disk | [0019](0019-media-in-dynamodb.md) |
| Gemini Vision for every photo (§17) | metadata only, user captions | [0021](0021-photos-metadata-only.md) |
| A local or Gemini embedding model | OpenAI `text-embedding-3-small` | [0006](0006-embeddings-768.md) |

## Adding a decision

When you make a choice someone could reasonably question later, add a record:

1. Copy the template below to `NNNN-short-name.md`, using the next number.
2. Keep it short: one screen is ideal.
3. Add it to the right table above.
4. If it replaces an older record, set the old one's status to
   `Superseded by [NNNN](NNNN-short-name.md)` and don't delete it. The history is the point.

```markdown
# NNNN. The decision as a short sentence

- **Status:** Accepted
- **Date:** YYYY-MM-DD

## Context

The problem, and the constraints that forced a choice.

## Decision

What was chosen, specifically, with the numbers.

## Consequences

What it costs, what it makes easy, and what to watch out for.

## Where in the code

The files to open next.
```
