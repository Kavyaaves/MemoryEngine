"""Turning evidence into an answer: ordering, confidence, the LLM prompt, and the no-AI fallback."""

import html

from app.schemas.api import Evidence

RELEVANCE_POOL = 8  # how many top results take part in first/last ordering


def order_evidence(evidence: list[Evidence], order: str | None) -> list[Evidence]:
    """For first/last questions: take the most relevant results, then sort those by date.

    (Sorting *all* results by date would put an irrelevant old "ok" message first.)
    """
    if order not in ("first", "last") or not evidence:
        return evidence
    pool, rest = evidence[:RELEVANCE_POOL], evidence[RELEVANCE_POOL:]
    dated = sorted((e for e in pool if e.timestamp), key=lambda e: e.timestamp, reverse=(order == "last"))
    undated = [e for e in pool if not e.timestamp]
    return dated + undated + rest


def heuristic_confidence(evidence: list[Evidence]) -> str:
    """high / medium / low / none — based on how many search paths agree on the top result."""
    if not evidence:
        return "none"
    top = evidence[0]
    agreeing_paths = len(set(top.retrieval_paths))
    if agreeing_paths >= 3 or (top.score >= 1.8 and len(evidence) >= 3):
        return "high"
    if agreeing_paths >= 2 or top.score >= 1.0:
        return "medium"
    return "low"


def format_evidence(evidence: list[Evidence]) -> str:
    """The numbered <evidence> block given to the LLM (PLAN §40 prompt-injection protection).

    Memory text is HTML-escaped, so a message containing "</memory> ignore previous
    instructions" cannot break out of its tag and pose as an instruction.
    """
    blocks = []
    for number, e in enumerate(evidence, start=1):
        when = e.timestamp.strftime("%Y-%m-%d %H:%M") if e.timestamp else "unknown date"
        where = e.conversation_title or e.source_name
        media = f' media="{",".join(m.kind for m in e.media)}"' if e.media else ""
        blocks.append(
            f'<memory id="{number}" source="{html.escape(e.source_type)}: {html.escape(where)}" date="{when}" '
            f'author="{html.escape(e.author or "unknown")}" lang="{e.language}"{media}>\n'
            f"{html.escape(e.text[:1500])}\n</memory>")
    return "<evidence>\n" + "\n".join(blocks) + "\n</evidence>"


def extractive_answer(evidence: list[Evidence], order: str | None, facts: list[str]) -> str:
    """The answer when no LLM is reachable: computed facts plus the top memories, cited."""
    if not evidence and not facts:
        return "I couldn't find any memories matching that question."
    lines = list(facts)
    if evidence:
        lead = {"first": "The earliest matching memory is",
                "last": "The most recent matching memory is"}.get(order or "", "The most relevant memories I found are")
        lines.append(f"{lead} (AI answer generation is currently unavailable, so these are shown directly):")
        for number, e in enumerate(evidence[:5], start=1):
            when = e.timestamp.strftime("%d %b %Y") if e.timestamp else "undated"
            lines.append(f"- {when} — {e.author or e.source_name}: “{e.snippet}” [{number}]")
    return "\n".join(lines)
