# Memory Engine docs: start here

Everything you need to understand this app: what it does, how it works, why it's built this way,
what every package is for, and how to explain it in an interview.

## What's in this folder

| Doc | Read it to… |
|---|---|
| [architecture.md](architecture.md) | follow an upload and a question through the whole system |
| [decisions/](decisions/README.md) | understand **why** each part is built the way it is (32 short records) |
| [packages/](packages/README.md) | learn what every package and service does, why it's needed, and its gotchas |
| [glossary.md](glossary.md) | look up a term (RRF, HNSW, embedding, SSE, JWT, …) |
| [faq.md](faq.md) | practise interview questions about this project, with answers |
| [deploy-free.md](deploy-free.md) | deploy the app on one AWS free-tier server, step by step |
| [api-contract.md](api-contract.md) | see every HTTP endpoint and its request and response shapes |

Outside this folder: [README.md](../README.md) (setup and status), [backend/README.md](../backend/README.md)
and [frontend/README.md](../frontend/README.md) (code maps), and [PLAN.md](../PLAN.md) (the
original plan, partly out of date; see [decisions/](decisions/README.md#where-planmd-is-out-of-date)).

---

## A learning path

Work through it in order. Each step lists what to read and what you should be able to explain afterwards.

### Step 1. The product (30 minutes)

- Read: the root [README.md](../README.md), then [architecture.md §1–2](architecture.md#1-the-big-picture).
- You can explain: what the app does, the four ideas behind it, and what a *memory* is.

### Step 2. An upload, end to end (1 hour)

- Read: [architecture.md §3](architecture.md#3-following-an-upload), then
  [0011](decisions/0011-incremental-ingestion.md), [0010](decisions/0010-multilingual-without-ai.md)
  and [0012](decisions/0012-entity-resolution-asks.md).
- Open: `backend/app/ingestion/pipeline.py`, then `parsers/whatsapp.py` and `multilingual/tanglish.py`.
- You can explain: why re-uploading a chat doesn't create duplicates, how Tamil script and Tanglish
  are matched without AI, and why "R" isn't merged with "Rahul" automatically.

### Step 3. A question, end to end (2 hours)

The core of the app.

- Read: [architecture.md §4](architecture.md#4-following-a-question), then
  [0007](decisions/0007-hybrid-retrieval-rrf.md), [0008](decisions/0008-reranking-stages.md),
  [0009](decisions/0009-sql-for-chronology.md), [0003](decisions/0003-langgraph-and-langchain.md)
  and [0014](decisions/0014-memories-are-untrusted.md).
- Open: `backend/app/agents/graph.py`, then `retrieval/hybrid.py`, `retrieval/fusion.py` and
  `retrieval/reranker.py`.
- Look up: *RAG*, *embedding*, *RRF*, *HNSW*, *MMR* in the [glossary](glossary.md).
- You can explain: the six search paths and why each exists, how RRF merges them, the three rerank
  stages, and why "first" questions use SQL.

### Step 4. Running on real infrastructure (1 hour)

- Read: [0001](decisions/0001-hosted-ai-only.md), [0002](decisions/0002-openai-behind-a-router.md),
  [0015](decisions/0015-graceful-degradation.md), [0016](decisions/0016-quota-guard-and-token-budget.md),
  [0017](decisions/0017-prompt-caching.md), [0018](decisions/0018-redis-and-arq-optional.md) and
  [0020](decisions/0020-security-model.md).
- You can explain: what happens when OpenAI is down or over budget, how costs are capped, and how
  private data is protected.

### Step 5. Everything else (1–2 hours)

- The Memory Universe: [architecture.md §6](architecture.md#6-the-memory-universe), [0026](decisions/0026-memory-universe.md).
- Photos, sentiment and fine-tuning: [0021](decisions/0021-photos-metadata-only.md),
  [0023](decisions/0023-local-sentiment-model.md), [0024](decisions/0024-one-derived-model.md),
  [0025](decisions/0025-address-terms-are-counting.md).
- Measuring: [0027](decisions/0027-evaluation.md), [0028](decisions/0028-observability.md).
- Frontend: [0029](decisions/0029-frontend-stack.md), [0030](decisions/0030-nginx-same-origin.md),
  [packages/frontend.md](packages/frontend.md).
- Deployment: [0031](decisions/0031-backend-docker-image.md), [0032](decisions/0032-free-tier-deployment.md),
  then try it for real with [deploy-free.md](deploy-free.md).

### Step 6. The tools (reference)

- Read [packages/backend.md](packages/backend.md) and [packages/frontend.md](packages/frontend.md)
  section by section as you meet each package in the code.

### Step 7. Explaining it (practice)

- Go through [faq.md](faq.md). Cover the answer, say your own out loud, then compare.

---

## Hands-on exercises

Run these from `backend/` after `python -m venv .venv` and `.venv/Scripts/pip install -e ".[dev]"`.
None of them needs a database, Redis or an API key.

**1. Run the whole test suite.** Everything runs offline, because OpenAI and DynamoDB are faked.

```bash
.venv/Scripts/pytest -q
```

**2. See how a Tamil-script message becomes searchable.** Start Python with `.venv/Scripts/python`, then:

```python
from app.multilingual.tanglish import process_text, expand_query

process_text("நான் அவன் கூட போனேன்").search_text
# 'நான் அவன் கூட போனேன் naan avan kooda ponen nan kuda'

expand_query("naan avan kooda pona")
# ['naan', 'avan', 'kooda', 'pona', 'நான்', 'nan', 'அவன்', 'கூட', 'kuda', 'போன']
```

The query and the message now share `naan`, `avan`, `kooda` and `nan`. That's
[0010](decisions/0010-multilingual-without-ai.md) in action. On Windows, if Tamil prints as `?`,
run `set PYTHONIOENCODING=utf-8` first.

**3. See why "R" isn't merged with "Rahul".**

```python
from app.people.aliases import normalize_alias, alias_similarity

normalize_alias("Rahul ❤️")          # 'rahul': identical after normalising, so merged automatically
alias_similarity("r", "rahul")       # 0.75: above 0.72, so the user is asked
alias_similarity("rahu", "rahul")    # 0.85: also asked
```

**4. Read one test as documentation.** Open `tests/test_multilingual.py` or `tests/test_reranking.py`.
Tests show exactly what each function promises.

**5. Change a setting and measure it** (needs a database with your data and an OpenAI key). Run the
pipeline comparison, set `MMR_LAMBDA=0.7` in `backend/.env`, run it again, and compare the tables.
See [0027](decisions/0027-evaluation.md).

```bash
.venv/Scripts/python -m app.evaluation.runner --user you@example.com --dataset eval/golden.jsonl
```

**6. Trace one question by hand.** Ask something in the app, open the Trace panel, and match each
step to a node in `agents/graph.py` and a path in `retrieval/hybrid.py`.

---

## Keeping these docs useful

- Made a choice someone could question later? Add a decision record ([how](decisions/README.md#adding-a-decision)).
- Added or removed a package? Update [packages/](packages/README.md#adding-upgrading-or-removing-a-package).
- Changed an endpoint? Update [api-contract.md](api-contract.md) and `frontend/src/types/api.ts`.
