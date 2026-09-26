"""The Ask agent: a LangGraph workflow (PLAN §14, §74).

    START → analyze → retrieve → verify ──(enough evidence, or tried twice)──→ answer → END
                         ↑          │
                         └──────────┘  (weak evidence: search again with new queries)

- analyze:  what is being asked? people, dates, first/last, photos?   (query_analysis.py)
- retrieve: resolve people, count if asked, run hybrid search         (tools.py)
            ("how do I call Nihal?" counts address words instead of searching: retrieval/address.py)
- verify:   is the evidence good enough? if not, suggest new queries
            (no LLM call when the LLM reranker already scored a passage 8/10 or higher)
- answer:   stream a cited answer from the LLM — or, with no AI, list the evidence (answering.py)

Every LLM step has a deterministic fallback, so the agent always returns *something* grounded.
Nodes receive shared objects (tools, router, emit, timer) through LangGraph's `config`.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agents.answering import extractive_answer, format_evidence, heuristic_confidence, order_evidence
from app.agents.query_analysis import heuristic_analysis, merge_analysis
from app.agents.tools import MemoryTools
from app.ai.prompts import ANALYZE_SYSTEM, ANSWER_SYSTEM, PROMPT_VERSION, VERIFY_SYSTEM
from app.ai.providers.base import AIUnavailable, ProviderError
from app.ai.providers.router import AIRouter
from app.core.timeutils import start_of_day
from app.finetuning import base_model
from app.observability.tracing import StepTimer
from app.schemas.ai import EvidenceVerdict, QueryAnalysis
from app.schemas.api import Evidence

Emit = Callable[[str, Any], Awaitable[None]]  # sends a progress event to the browser (SSE)
MAX_SEARCH_ATTEMPTS = 2
# verify is skipped when the LLM reranker gave the best passage at least this score (8/10:
# above "part of the answer", see RERANK_SYSTEM in ai/prompts).
SKIP_VERIFY_MIN_RERANK_SCORE = 0.8
MEDIA_SOURCE_TYPES = {"image": "image", "audio": "audio", "video": "video"}
NO_EVIDENCE_ANSWER = ("I couldn't find memories that answer this. Try different words, a person's name, "
                      "or a time period (e.g. “in 2023”).")


class AgentState(TypedDict, total=False):
    question: str
    history: list[tuple[str, str]]  # earlier chat turns: (role, text)
    analysis: QueryAnalysis
    person_ids: list[uuid.UUID]
    person_names: list[str]
    evidence: list[Evidence]
    rerank_top_score: float | None  # the LLM reranker's best score (0..1) for this evidence, if it ran
    facts: list[str]  # things computed by SQL, e.g. "FACT: 42 memories …"
    queries: list[str]  # search queries to use (rewrites / alternatives)
    attempts: int
    sufficient: bool
    confidence: str
    answer: str
    provider: str | None
    model: str | None
    degraded: bool  # True when an AI step fell back to the no-AI path
    derived_model: str | None  # the fine-tuning phase's derived model, if a step used it (app/finetuning/)


# ---- helpers to read the shared objects out of `config` ----------------------------------

def _tools(config: RunnableConfig) -> MemoryTools:
    return config["configurable"]["tools"]


def _router(config: RunnableConfig) -> AIRouter:
    return config["configurable"]["router"]


def _timer(config: RunnableConfig) -> StepTimer:
    return config["configurable"]["timer"]


async def _emit(config: RunnableConfig, event: str, data: Any) -> None:
    emit: Emit | None = config["configurable"].get("emit")
    if emit:
        await emit(event, data)


# ---- nodes ---------------------------------------------------------------------------------

async def analyze(state: AgentState, config: RunnableConfig) -> AgentState:
    tools, router = _tools(config), _router(config)
    await _emit(config, "step", {"name": "analyze", "detail": "Understanding the question"})
    with _timer(config).step("analyze") as step:
        rules = heuristic_analysis(state["question"], await tools.known_aliases())
        llm = None
        if router.available("rewrite"):
            earlier_turns = "\n".join(f"{role}: {text}" for role, text in state.get("history", [])[-4:])
            # Today's date goes in the user message, so the system prompt stays identical (cacheable).
            prompt = f"Today's date: {date.today().isoformat()}\n\n" \
                + (f"Conversation so far:\n{earlier_turns}\n\n" if earlier_turns else "") \
                + f"Question: {state['question']}"
            try:
                llm = await router.structured("rewrite", QueryAnalysis, [
                    ("system", ANALYZE_SYSTEM), ("user", prompt)], user_id=tools.user_id)
            except AIUnavailable:
                llm = None
        analysis = merge_analysis(rules, llm)
        step["detail"] = (f"intent={analysis.intent} people={analysis.people} order={analysis.temporal_order}"
                          + ("" if llm else " (rules only)"))
    return {"analysis": analysis, "attempts": 0, "queries": analysis.rewritten_queries, "facts": []}


async def retrieve(state: AgentState, config: RunnableConfig) -> AgentState:
    tools = _tools(config)
    analysis = state["analysis"]
    is_retry = state.get("attempts", 0) >= 1
    await _emit(config, "step", {"name": "retrieve",
                                 "detail": "Searching again with new queries" if is_retry else "Searching memories"})
    with _timer(config).step("retrieve") as step:
        # People: take the best match for each name.
        person_ids, person_names = [], []
        for name in analysis.people:
            for person_id, display_name, _score in (await tools.resolve_person(name))[:1]:
                person_ids.append(person_id)
                person_names.append(display_name)

        start, end = start_of_day(analysis.time_start), start_of_day(analysis.time_end)
        if is_retry and not state.get("evidence"):
            start = end = None  # nothing found — maybe the time window was wrong, so widen it
        source_types = [MEDIA_SOURCE_TYPES[m] for m in analysis.modality if m in MEDIA_SOURCE_TYPES]

        facts = list(state.get("facts", []))
        if analysis.intent == "count" and not is_retry:
            topic = " ".join(analysis.topic_keywords) or None
            count = await tools.count_memories(topic, start=start, end=end, person_ids=person_ids)
            about = f" matching '{topic}'" if topic else ""
            involving = f" involving {', '.join(person_names)}" if person_names else ""
            facts.append(f"FACT (computed by SQL): {count} memories{about}{involving} in the selected period.")

        # "How do I call Nihal?": count the address words in the chat instead of searching (retrieval/address.py).
        address_evidence, used_derived = [], state.get("derived_model")
        if analysis.intent == "address" and person_ids and not is_retry:
            fact, address_evidence, used_derived = await tools.address_terms(
                person_ids[0], person_names[0], speaker=analysis.address_speaker or "self")
            if fact:
                facts.append(fact)

        if address_evidence:
            evidence, rerank_top_score, degraded = address_evidence, None, False
            method = f"the derived model {used_derived}" if used_derived else "the word list"
            step["detail"] = (f"counted address words for {person_names[0]} with {method}; "
                              f"{len(evidence)} example messages")
        else:
            search = dict(start=start, end=end, person_ids=person_ids, extra_queries=state.get("queries"),
                          order=analysis.temporal_order)
            result = await tools.search_memories(state["question"], source_types=source_types, **search)
            if source_types and not result.evidence:
                result = await tools.search_memories(state["question"], **search)  # no media indexed → use text
            evidence = order_evidence(result.evidence, analysis.temporal_order)
            rerank_top_score, degraded = result.top_rerank_score, result.degraded
            step["detail"] = f"{len(evidence)} results via {result.path_counts}"

    await _emit(config, "evidence", [e.model_dump(mode="json") for e in evidence])
    return {"evidence": evidence, "rerank_top_score": rerank_top_score, "person_ids": person_ids,
            "person_names": person_names, "facts": facts, "attempts": state.get("attempts", 0) + 1,
            "degraded": state.get("degraded", False) or degraded, "derived_model": used_derived}


async def verify(state: AgentState, config: RunnableConfig) -> AgentState:
    tools, router = _tools(config), _router(config)
    await _emit(config, "step", {"name": "verify", "detail": "Checking the evidence"})
    evidence = state.get("evidence", [])
    with _timer(config).step("verify") as step:
        confidence = heuristic_confidence(evidence)
        sufficient = confidence in ("high", "medium") or bool(state.get("facts"))
        alternatives: list[str] = []
        rerank_top_score = state.get("rerank_top_score")
        if state["analysis"].intent == "address" and state.get("facts"):
            # The address words were counted over the whole chat; a model can't improve on exact counts.
            sufficient, confidence = True, "high"
            step["detail"] = "skipped: address words counted by SQL"
        elif not evidence:
            sufficient, confidence = bool(state.get("facts")), "none"
            keywords = state["analysis"].topic_keywords
            alternatives = [" ".join(keywords)] if keywords else []
        elif rerank_top_score is not None and rerank_top_score >= SKIP_VERIFY_MIN_RERANK_SCORE:
            # The reranker's model has just read these passages and found one that answers the
            # question — asking a model again "is this enough?" would cost a round trip for the same verdict.
            sufficient, confidence = True, "high"
            step["detail"] = f"skipped: the reranker scored the best passage {round(rerank_top_score * 10)}/10"
        elif router.available("fast"):
            try:
                verdict = await router.structured("fast", EvidenceVerdict, [
                    ("system", VERIFY_SYSTEM),
                    ("user", f"Question: {state['question']}\n\n{format_evidence(evidence[:8])}")],
                    user_id=tools.user_id)
                sufficient, confidence, alternatives = verdict.sufficient, verdict.confidence, verdict.alternative_queries
            except AIUnavailable:
                pass  # keep the heuristic verdict
        step.setdefault("detail", f"sufficient={sufficient} confidence={confidence}")
    return {"sufficient": sufficient, "confidence": confidence, "queries": alternatives or state.get("queries", [])}


def search_again_or_answer(state: AgentState) -> str:
    if state.get("sufficient") or state.get("attempts", 0) >= MAX_SEARCH_ATTEMPTS:
        return "answer"
    return "retrieve"


def _answer_prompt(state: AgentState) -> list[tuple[str, str]]:
    """[system, *earlier turns, user]: ordered from never-changing to always-changing.

    OpenAI's prompt cache reuses the longest identical start of a prompt, so the fixed system
    prompt comes first, then the conversation so far (identical between turns of one chat),
    and the evidence and question — different every time — come last.
    """
    analysis = state["analysis"]
    order_note = {"first": "Evidence is sorted oldest → newest; the earliest supported item is [1].",
                  "last": "Evidence is sorted newest → oldest; the most recent supported item is [1]."
                  }.get(analysis.temporal_order or "", "")
    people_note = f"Resolved people: {', '.join(state['person_names'])}." if state.get("person_names") else ""
    user_message = "\n".join(part for part in [
        format_evidence(state.get("evidence", [])),
        "\n".join(state.get("facts", [])),
        order_note,
        people_note,
        f"Evidence confidence estimate: {state.get('confidence', 'low')}.",
        f"Question: {state['question']}",
    ] if part)
    earlier_turns = [(role, text[:2000]) for role, text in state.get("history", [])[-6:]]
    return [("system", ANSWER_SYSTEM), *earlier_turns, ("user", user_message)]


async def answer(state: AgentState, config: RunnableConfig) -> AgentState:
    tools, router = _tools(config), _router(config)
    await _emit(config, "step", {"name": "answer", "detail": "Writing a grounded answer"})
    evidence, facts = state.get("evidence", []), state.get("facts", [])

    with _timer(config).step("answer", prompt_version=PROMPT_VERSION) as step:
        if not evidence and not facts:
            await _emit(config, "token", {"text": NO_EVIDENCE_ANSWER})
            step["detail"] = "no evidence"
            return {"answer": NO_EVIDENCE_ANSWER, "confidence": "none", "provider": None, "model": None}

        used = {"provider": None, "model": None}

        def remember_provider(provider: str, model: str) -> None:
            used.update(provider=provider, model=model)

        chunks: list[str] = []
        degraded = state.get("degraded", False)
        try:
            async for chunk in router.stream("reasoning", _answer_prompt(state), user_id=tools.user_id,
                                             on_provider=remember_provider):
                chunks.append(chunk)
                await _emit(config, "token", {"text": chunk})
            text = "".join(chunks).strip()
        except (AIUnavailable, ProviderError) as exc:
            # No model reachable (or the stream broke mid-answer): list the evidence instead.
            degraded = True
            fallback = extractive_answer(evidence, state["analysis"].temporal_order, facts)
            separator = "\n\n" if chunks else ""
            await _emit(config, "token", {"text": separator + fallback})
            text = ("".join(chunks) + separator + fallback).strip()
            step["detail"] = f"degraded: {str(exc)[:200]}"
    return {"answer": text, "provider": used["provider"], "model": used["model"], "degraded": degraded}


# ---- wiring --------------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("analyze", analyze)
    graph.add_node("retrieve", retrieve)
    graph.add_node("verify", verify)
    graph.add_node("answer", answer)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_edge("retrieve", "verify")
    graph.add_conditional_edges("verify", search_again_or_answer, {"retrieve": "retrieve", "answer": "answer"})
    graph.add_edge("answer", END)
    return graph.compile()


AGENT = build_graph()  # compiled once; everything request-specific is passed in `config`


async def run_agent(*, question: str, history: list[tuple[str, str]], tools: MemoryTools, router: AIRouter,
                    emit: Emit | None = None) -> dict:
    """Run the agent and return a dict shaped like the API's AskOut."""
    timer = StepTimer()
    config = {"configurable": {"tools": tools, "router": router, "emit": emit, "timer": timer},
              "recursion_limit": 12}
    state: AgentState = await AGENT.ainvoke({"question": question, "history": history}, config=config)

    analysis: QueryAnalysis = state["analysis"]
    evidence = state.get("evidence", [])
    return {
        "answer": state.get("answer", ""),
        "evidence": evidence,
        "confidence": state.get("confidence", "none") if evidence else "none",
        "analysis": {"intent": analysis.intent, "people": analysis.people, "time_start": analysis.time_start,
                     "time_end": analysis.time_end, "temporal_order": analysis.temporal_order,
                     "modality": list(analysis.modality),
                     "rewritten_queries": state.get("queries", analysis.rewritten_queries)},
        "trace": {"steps": [{"name": s["name"], "latency_ms": s.get("latency_ms", 0), "detail": s.get("detail")}
                            for s in timer.steps],
                  "provider": state.get("provider"), "model": state.get("model"),
                  "degraded": bool(state.get("degraded")),
                  # the two fine-tuning labels, when the derived model helped: where it came from, and what it is
                  "finetune": ({"base_model": base_model(), "derived_model": state["derived_model"]}
                               if state.get("derived_model") else None)},
    }
