# 0009. SQL does counting and chronology, never the LLM

- **Status:** Accepted

## Context

Many memory questions are about time or numbers: "When did I first say…", "How many times…",
"What did we talk about before the trip?". LLMs are unreliable at sorting dates and counting across
many passages, and they only ever see the top few results anyway.

## Decision

- Counting, date ranges and "first / last" are SQL queries (`ORDER BY timestamp`, `COUNT(*)`). They
  are agent tools the LangGraph agent calls.
- The question analyser extracts the time window and the order ("first", "last") so the right SQL
  tool is used.
- The LLM only writes the final answer from evidence that is already sorted and counted.

## Consequences

- "First" answers are correct even when the earliest message isn't the most relevant-looking one.
- Answers say exactly how many messages were counted, which the LLM couldn't know.
- Questions that are really counting, like "how do I call X?", need their own tool
  ([0025](0025-address-terms-are-counting.md)).

## Where in the code

`backend/app/agents/tools.py`, `retrieval/temporal.py`, `agents/query_analysis.py`. PLAN.md §11.
