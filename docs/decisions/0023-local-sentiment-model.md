# 0023. Sentiment from a small local model: TamilSense on the CPU

- **Status:** Accepted. The one exception to [0001](0001-hosted-ai-only.md).

## Context

Mood over time ("was I happier last year?") needs a sentiment label on every message, and a chat
history has tens of thousands of them. One hosted LLM call per message would be slow and expensive,
and general models handle Tanglish poorly.

## Decision

- Use `vishnuexe/TamilSense-model` from Hugging Face: Google's MuRIL (a BERT model for Indian
  languages) fine-tuned on Tamil and Tanglish. It is not an LLM. It's a classifier that runs on the
  CPU, so no text leaves the server and it costs nothing per message.
- It only knows *positive* and *negative*. Below a confidence of 0.75 (`SENTIMENT_NEUTRAL_BELOW`)
  the text is labelled *neutral*, because "ok da" is neither.
- The model is loaded once per process and kept in memory. Texts are classified in batches of 32 and
  cut to 512 tokens (BERT's limit).
- New memories are analysed right after each import. Results go in `memory.meta["sentiment"]`, so
  no schema change is needed.
- It is optional: the `.[sentiment]` extra locally, a build argument in Docker
  ([0031](0031-backend-docker-image.md)). Without it, sentiment is simply skipped.

## Consequences

- The model is about 1 GB on disk and needs about 1 GB of RAM in each container that loads it
  (the worker, and the API for the AI Lab "Analyse" button).
- That doesn't fit a 1 GB server, so the free-tier deploy turns it off ([0032](0032-free-tier-deployment.md)).

## Where in the code

`backend/app/sentiment/` (`model.py`, `pipeline.py`, `__main__.py`), `api/sentiment.py`,
`retrieval/evidence.py` (each evidence card shows its sentiment).
