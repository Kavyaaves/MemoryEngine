# 0014. Retrieved memories are untrusted data, never instructions

- **Status:** Accepted

## Context

The evidence put into a prompt is the user's own messages, and also messages other people sent them.
Any of them can contain text like "Ignore previous instructions…". This is **prompt injection**: if
the model treats that text as an instruction, one forwarded message could change how the agent behaves.

## Decision

- Retrieved memories are HTML-escaped and wrapped in `<memory>` tags inside the prompt.
- Every system prompt says that text inside those tags is evidence to read, never instructions to follow.
- The order is fixed: system instructions → the user's question → retrieved memories as untrusted
  evidence. Retrieved text can't close the tag or add a new role, because it is escaped.
- The agent never exposes its chain of thought. It shows sources, dates, snippets and confidence instead.

## Consequences

- One message can't take over the agent. This lowers the risk but doesn't remove it completely, so
  prompt-injection tests are on the roadmap (PLAN.md §49).

## Where in the code

`backend/app/ai/prompts/`, `agents/answering.py`, `retrieval/reranker.py`. PLAN.md §16 and §40.
