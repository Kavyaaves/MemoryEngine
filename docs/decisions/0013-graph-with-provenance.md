# 0013. Graph edges carry their evidence; inferred is never shown as fact

- **Status:** Accepted

## Context

A knowledge graph ("Rahul KNOWS Priya", "this photo is PART_OF the Kerala trip") is useful for
retrieval, but many edges are guesses. If a guess is stored the same way as a fact, the agent later
repeats it as fact.

## Decision

- Relationships are stored explicitly in one `relationships` table. Each row is a generic edge
  between two nodes addressed by `(type, id)`, such as `(PERSON, rahul) —KNOWS→ (PERSON, priya)`.
  The types include `PART_OF`, `KNOWS`, `MENTIONED`, and `APPEARS_IN` / `RELATED_TO`, which the
  Memory Universe adds.
- **Every edge carries** `confidence`, `created_by` (`parser:…`, `ai:<model>`, `user` or `universe`)
  and `source_memory_id` (the memory that supports it).
- The first edges are the cheap, certain ones: PERSON –PART_OF→ CONVERSATION and
  PERSON –KNOWS→ PERSON from who talks in which chat, plus mention detection.
- Answers separate FACT, AI-INFERRED and UNCERTAIN, and AI-generated groupings (occasions, book
  titles) keep the memories that support them.

## Consequences

- Any edge can be traced back to the message behind it, and wrong edges can be removed by source.
- The graph path in retrieval ([0007](0007-hybrid-retrieval-rrf.md)) can weigh edges by confidence.

## Where in the code

`backend/app/models/graph.py`, `ingestion/graph_builder.py`, `retrieval/graph.py`,
`universe/graph.py`. PLAN.md §12, §31, §32.
