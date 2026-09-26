"""Reranking: re-order the merged candidates using more signals (PLAN §9, §20E).

Two stages (RERANKER setting):
- heuristic_score: cheap, deterministic, always on (unless RERANKER=none, an eval baseline).
- llm_rerank:      RERANKER=llm (the default) — the fast OpenAI model reads the top passages and
                   scores each 0–10 for how well it answers the question. This catches meaning
                   the keyword signals miss (a Tanglish question vs. a Tamil-script message).
                   If no model is reachable, the heuristic order is kept.
An optional third stage, diversity.py (MMR), spreads out near-duplicates afterwards.
"""

import html
import re

from pydantic import BaseModel, Field

from app.ai.prompts import RERANK_SYSTEM
from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import AIRouter
from app.multilingual.normalization import phonetic_key
from app.retrieval.fusion import FusedCandidate
from app.retrieval.query import content_terms

# How much each signal counts. The fused RRF score is tiny (~0.01–0.05), hence the big multiplier.
WEIGHT_FUSION = 30.0
WEIGHT_TERM_COVERAGE = 0.9  # share of query words present in the memory
WEIGHT_EXACT_PHRASE = 0.5  # the whole query appears verbatim
WEIGHT_PATH_AGREEMENT = 0.4  # found by several search paths
WEIGHT_SEMANTIC = 0.6  # vector similarity
PENALTY_TINY_MESSAGE = 0.15  # "ok", "hmm" rarely answer anything

# After the LLM has scored a passage, its score dominates; the heuristic breaks ties.
WEIGHT_HEURISTIC_AFTER_LLM = 0.5
WEIGHT_LLM = 2.0
LLM_PASSAGE_CHARS = 500  # enough to judge relevance, short enough to keep the call fast and cheap


def heuristic_score(candidate: FusedCandidate, search_text: str, text: str, query_terms: list[str],
                    query_phrase: str) -> float:
    terms = content_terms(query_terms)
    memory_words = set(search_text.split())
    memory_sounds = {phonetic_key(w) for w in memory_words if w.isascii()}

    coverage = 0.0
    if terms:
        present = [t for t in terms if t in memory_words or (t.isascii() and phonetic_key(t) in memory_sounds)]
        coverage = len(present) / len(terms)
    exact_phrase = len(query_phrase) > 4 and query_phrase in search_text
    agreement = min(len(set(candidate.paths)), 4) / 4
    semantic = candidate.path_scores.get("vector", 0.0)
    is_tiny = len(re.findall(r"\w+", text)) <= 2

    return (WEIGHT_FUSION * candidate.score
            + WEIGHT_TERM_COVERAGE * coverage
            + WEIGHT_EXACT_PHRASE * exact_phrase
            + WEIGHT_PATH_AGREEMENT * agreement
            + WEIGHT_SEMANTIC * semantic
            - PENALTY_TINY_MESSAGE * is_tiny)


def combined_score(heuristic: float, llm: float) -> float:
    """The final score of a passage the LLM has judged (llm is 0..1)."""
    return WEIGHT_HEURISTIC_AFTER_LLM * heuristic + WEIGHT_LLM * llm


class Passage(BaseModel):
    text: str
    date: str | None = None  # "2024-06-14"
    author: str | None = None


class _PassageScores(BaseModel):
    scores: list[int] = Field(description="relevance 0-10 for each passage, same order")


def format_passages(passages: list[Passage]) -> str:
    """Numbered passages for the reranking prompt. Text is escaped so it can't close its tag."""
    blocks = []
    for number, p in enumerate(passages):
        date = f' date="{p.date}"' if p.date else ""
        author = f' author="{html.escape(p.author)}"' if p.author else ""
        blocks.append(f"<passage id={number}{date}{author}>{html.escape(p.text[:LLM_PASSAGE_CHARS])}</passage>")
    return "\n".join(blocks)


async def llm_rerank(router: AIRouter, question: str, passages: list[Passage], user_id=None) -> list[float] | None:
    """Scores 0..1 per passage, or None if no model is available (keep the heuristic order)."""
    if not passages or not router.available("fast"):
        return None
    try:
        result = await router.structured("fast", _PassageScores, [
            ("system", RERANK_SYSTEM),
            ("user", f"Question: {question}\n\n{format_passages(passages)}"),
        ], user_id=user_id)
    except AIUnavailable:
        return None
    if len(result.scores) != len(passages):
        return None  # the model miscounted — don't trust it
    return [min(max(score, 0), 10) / 10 for score in result.scores]
