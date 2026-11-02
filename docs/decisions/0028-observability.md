# 0028. Observability: a trace in every answer, OpenTelemetry and LangSmith opt-in

- **Status:** Accepted

## Context

When an answer is wrong you need to know which step failed: the question analysis, one search path,
the reranker or the answer model. External tracing services are useful but shouldn't be required to run the app.

## Decision

- **User-visible trace.** Every answer carries the steps it took, each with its latency and details
  (how many candidates per path, which model, tokens, whether the derived model was used). Ask shows
  it in the Trace panel, and the retrieval paths per evidence card.
- **OpenTelemetry**, only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set: spans for each step plus
  automatic FastAPI request spans, sent over OTLP. It needs the `.[otel]` extra, which Docker installs.
- **LangSmith**, only when `LANGSMITH_API_KEY` is set: LangChain and LangGraph runs are traced automatically.
- AI usage per call is in the `ai_usage` table ([0016](0016-quota-guard-and-token-budget.md)).

## Consequences

- Nothing is sent anywhere unless you configure it.
- One `StepTimer` feeds both the user-visible trace and the spans, so they always agree.

## Where in the code

`backend/app/observability/tracing.py`, `agents/graph.py`, `frontend/src/features/chat/TracePanel.tsx`,
`features/chat/RetrievalPaths.tsx`. PLAN.md §38.
