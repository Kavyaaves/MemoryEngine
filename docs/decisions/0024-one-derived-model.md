# 0024. Fine-tuning: one derived model, trained task by task, always optional

- **Status:** Accepted

## Context

Fine-tuning is part of the learning roadmap, but the app must never depend on a paid fine-tuned
model, and there are no local models to train ([0001](0001-hosted-ai-only.md)). Training a separate
model per skill would mean many model IDs to manage, and retraining one skill would forget the others.

## Decision

- Fine-tuning is hosted (OpenAI). The **base model** is a dated snapshot, `gpt-4.1-nano-2025-04-14`.
- There is **one derived model**. Every training run starts from the current derived model, not the
  base, and includes the data of **every task**. That way a new skill doesn't make it forget an old one.
  Each run's result replaces `FINETUNE_DERIVED_MODEL`, and `lineage.json` keeps the history.
- A **task** is one skill, with its own system prompt, labelled data, evaluation and use. The first
  task is `address_tagger` ([0025](0025-address-terms-are-counting.md)).
- Labels come from a bigger "teacher" model (`gpt-4.1`). User corrections become the gold set.
- Commands: `label → build → train → status → evaluate → apply`, each `python -m app.finetuning …`.
- **Nothing depends on the derived model.** Without it, every task uses its no-AI baseline.
  Answers that used it say so: a `finetune` field in the trace and a "derived model" badge in Ask.

## Consequences

- Every task is evaluated against its baseline, so it is clear whether training helped.
- The model runs at import time (`apply`), never per question, so it adds no latency to answers.

## Where in the code

`backend/app/finetuning/` (`__init__.py` explains it all, `__main__.py`, `training.py`, `data.py`,
`tasks/address_tagger/`). PLAN.md §20–21.
