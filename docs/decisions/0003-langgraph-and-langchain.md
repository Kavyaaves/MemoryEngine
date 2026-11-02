# 0003. LangGraph runs the Ask agent, LangChain talks to the models

- **Status:** Accepted

## Context

Answering a question takes several steps: understand the question, search, check whether the evidence
is good enough, maybe search again, then write the answer. That is a loop with state, not a single
prompt. We needed one orchestration framework, and a standard interface to chat models with
structured output.

## Decision

- **LangGraph** is the only orchestration layer. The Ask agent is a LangGraph state machine:
  `analyze → retrieve → verify ⟲ → answer`.
- **LangChain** provides the model interface (`ChatOpenAI`), structured output and the text splitter
  for long documents.
- CrewAI or any second agent framework is not used in production. It may only appear as a learning
  experiment.

## Consequences

- The agent's steps are explicit nodes that can be tested one by one with fake models.
- The `verify` step can loop back to `retrieve` when the evidence is weak. It skips its own LLM call
  when the reranker already scored a passage 8/10 or higher.
- LangSmith tracing works out of the box when `LANGSMITH_API_KEY` is set ([0028](0028-observability.md)).

## Where in the code

`backend/app/agents/graph.py` (start here), `agents/tools.py`, `agents/answering.py`,
`ai/providers/langchain_utils.py`. PLAN.md §14.
