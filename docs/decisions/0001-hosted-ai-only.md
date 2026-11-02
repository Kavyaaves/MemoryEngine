# 0001. Hosted AI only, no local LLMs

- **Status:** Accepted (one exception: [0023](0023-local-sentiment-model.md))

## Context

The app has to run as an ordinary hosted web app on a small server. Running a language model locally
(Ollama, vLLM, llama.cpp, a local GPU) would need far more RAM and compute than that server has, and
would make the whole app depend on a GPU being available.

## Decision

Every language-model call (answers, question understanding, reranking, transcription, embeddings) goes
to a hosted API. The app never depends on a local LLM. Everything else stays under our control:
application state, retrieval, orchestration, media storage, evaluation and business logic.

Small non-LLM models may still run locally when they are cheap and useful. The sentiment model is the
only one today.

## Consequences

- The backend runs on a 1 GB server and needs no GPU.
- Every AI call costs money and can fail or be rate-limited, which is why the app has quota limits
  ([0016](0016-quota-guard-and-token-budget.md)) and works without AI ([0015](0015-graceful-degradation.md)).
- Personal text is sent to the AI provider for the features that use AI. Keyword search, multilingual
  matching and sentiment never send text anywhere.

## Where in the code

`backend/app/ai/` (the only place that talks to an AI provider). PLAN.md §2 and §21.
