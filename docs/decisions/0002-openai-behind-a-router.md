# 0002. OpenAI for every AI task, behind one router

- **Status:** Accepted. Supersedes PLAN.md §2 and §22, where Gemini was primary and Groq the fallback.
- **Date:** 2026-09-26

## Context

The first plan used Gemini as the main provider and Groq as a fast fallback. In practice that meant
two free-tier quotas, two sets of models with different strengths, and embeddings that couldn't be
compared if they came from different providers. A paid OpenAI key covers every task (chat, structured
output, embeddings, speech-to-text, fine-tuning) with one billing account.

## Decision

- OpenAI is the provider for every task. The models are set in `.env`: `gpt-4.1-mini` writes answers,
  `gpt-4.1-nano` handles quick jobs (understanding the question, reranking, checking evidence),
  `gpt-4o-mini-transcribe` turns audio into text, and `text-embedding-3-small` makes the vectors.
- All calls go through one `AIRouter`. Nothing else in the app calls a provider directly.
- The router takes a **list** of providers per task (today always `["openai"]`). Adding a fallback
  later only means adding a provider and editing that list. No caller changes.
- For each provider, the router skips it if it is unconfigured or over quota, otherwise tries it, and
  tries once more on a transient error. If every provider fails it raises `AIUnavailable`.

## Consequences

- One API key and one bill. Gemini and Groq code was removed.
- If OpenAI is down, AI features are down. The app still works without them ([0015](0015-graceful-degradation.md)).
- Chat calls go through LangChain's `ChatOpenAI` ([0003](0003-langgraph-and-langchain.md)). Embeddings,
  speech and fine-tuning use the OpenAI SDK directly.

## Where in the code

`backend/app/ai/providers/router.py` (`DEFAULT_ROUTING`), `ai/providers/openai.py`, `ai/providers/base.py`.
