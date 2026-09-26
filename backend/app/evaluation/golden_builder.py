"""Build a test set ("golden dataset") from your own memories, for the evaluation runner.

    python -m app.evaluation.golden_builder --user you@example.com --count 150 --out eval/golden.jsonl

How it works:
  1. pick `count` random memories with enough text to ask about (a single "ok" can't be a test)
  2. for each, the answer model writes the question you might ask later that this memory answers,
     plus a short reference answer — in one of three styles, taken in turn:
        english    a paraphrase in English (few shared words: tests semantic search)
        tanglish   the way you'd type it casually in romanised Tamil
        keywords   a short search-box query
  3. write one JSON line per usable question: the memory's content_hash is the "relevant" answer

The memory the question was written from is the only one marked relevant, although others might
answer it too. That makes every score a slight *under*estimate — but the same one for every
pipeline, so comparisons between pipelines stay fair. Read through the file (each line has a
`source_preview`) and delete questions that don't make sense before relying on the numbers.
"""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select

from app.ai.prompts import GOLDEN_QUESTION_SYSTEM
from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import AIRouter, get_router
from app.db import SessionLocal
from app.models import Memory, User
from app.schemas.ai import GeneratedQuestion

STYLES = {
    "english": "a natural English question that paraphrases the memory — use different words for its key ideas",
    "tanglish": "a casual question in Tanglish (Tamil written in English letters), the way the user would type it",
    "keywords": "a short search-box query of 2 to 5 words (no question mark)",
}
MIN_CHARS = 25  # shorter memories rarely support a question only they answer
MAX_CHARS = 1500
PARALLEL_REQUESTS = 5  # questions written at the same time
PREVIEW_CHARS = 120


def question_prompt(text: str, author: str | None, date: str | None, source_type: str, style: str) -> str:
    return (f"Memory ({source_type}, author: {author or 'unknown'}, date: {date or 'unknown'}):\n"
            f"<memory>{text[:MAX_CHARS]}</memory>\n\n"
            f"Write the question as {STYLES[style]}.")


def dataset_line(number: int, style: str, content_hash: str, text: str, generated: GeneratedQuestion) -> dict:
    return {"id": f"gen-{number}", "category": style, "question": generated.question.strip(),
            "relevant": [content_hash], "reference_answer": generated.reference_answer.strip(),
            "source_preview": text[:PREVIEW_CHARS]}


async def sample_memories(session, user_id, count: int) -> list:
    """Random memories with enough text. Two extra per question, since some come back unusable."""
    query = (select(Memory.content_hash, Memory.text, Memory.author_raw, Memory.timestamp, Memory.source_type)
             .where(Memory.user_id == user_id, func.length(Memory.text).between(MIN_CHARS, MAX_CHARS))
             .order_by(func.random()).limit(count * 3))
    rows = (await session.execute(query)).all()
    unique_texts, memories = set(), []
    for row in rows:  # the same message forwarded to three groups is one test, not three
        if row.text not in unique_texts:
            unique_texts.add(row.text)
            memories.append(row)
    return memories


async def write_question(router: AIRouter, memory, style: str, user_id) -> GeneratedQuestion | None:
    date = memory.timestamp.date().isoformat() if memory.timestamp else None
    try:
        return await router.structured("reasoning", GeneratedQuestion, [
            ("system", GOLDEN_QUESTION_SYSTEM),
            ("user", question_prompt(memory.text, memory.author_raw, date, memory.source_type, style))],
            user_id=user_id)
    except AIUnavailable:
        return None


async def build(email: str, count: int, router: AIRouter) -> list[dict]:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one()
        memories = await sample_memories(session, user.id, count)

    styles = list(STYLES)
    lines: list[dict] = []
    # PARALLEL_REQUESTS questions are written at a time; stop once there are enough usable ones (saves API calls).
    for start in range(0, len(memories), PARALLEL_REQUESTS):
        group = memories[start:start + PARALLEL_REQUESTS]
        group_styles = [styles[(start + i) % len(styles)] for i in range(len(group))]
        results = await asyncio.gather(*(write_question(router, m, s, user.id)
                                         for m, s in zip(group, group_styles, strict=True)))
        for memory, style, generated in zip(group, group_styles, results, strict=True):
            if generated and generated.usable and generated.question.strip() and len(lines) < count:
                lines.append(dataset_line(len(lines) + 1, style, memory.content_hash, memory.text, generated))
        print(f"{len(lines)}/{count} questions")
        if len(lines) >= count:
            break
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", required=True, help="email of the account whose memories to use")
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--out", default="eval/golden.jsonl")
    parser.add_argument("--force", action="store_true", help="overwrite --out if it already exists")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists — pass --force to overwrite it (it may hold your hand-checked edits)")
    lines = asyncio.run(build(args.user, args.count, get_router()))
    header = ("// Generated by app.evaluation.golden_builder from your own memories. Review it: delete lines\n"
              "// whose question doesn't make sense. Keep this file private — it quotes your messages.\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8")
    print(f"wrote {len(lines)} questions to {out}")


if __name__ == "__main__":
    main()
