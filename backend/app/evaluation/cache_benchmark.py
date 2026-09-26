"""Measure what OpenAI's prompt caching does for the answer step: latency and cached tokens.

    python -m app.evaluation.cache_benchmark --rounds 10

Each round sends two answer requests shaped like the real ones (system prompt + 12 evidence
memories + a question). The evidence and question change on every request — as in real use —
so only the fixed system prompt at the start can be served from the cache:

    cold   the system prompt starts with a random request id, so its start never matches an
           earlier request → nothing can be cached (this is what an uncached prompt costs)
    warm   the system prompt is exactly the app's ANSWER_SYSTEM → after the first request its
           ~1,200 tokens can be served from the cache

Requests ask for only a few output tokens, so the time measured is mostly the time to *read*
the prompt — the part caching speeds up. Cold and warm alternate, so a slow minute on OpenAI's
side affects both equally. The evidence is invented (no personal data is sent).

Expect a modest difference: the cached prefix is ~1,200 of ~2,500 prompt tokens. Caching pays
off more in long chats, where the earlier turns are repeated (and cached) with each question.
"""

import argparse
import asyncio
import random
import time
import uuid

from app.ai.prompts import ANSWER_SYSTEM
from app.ai.providers.router import AIRouter, get_router
from app.evaluation.metrics import percentile
from app.evaluation.report import markdown_table, run_settings, write_report

EVIDENCE_MEMORIES = 12  # the default number of results the agent passes to the answer step
OUTPUT_TOKENS = 16  # keep generation short: we are timing how fast the prompt is read
PEOPLE = ["Rahul", "Priya", "Amma", "Karthik", "Divya"]
PLACES = ["Kerala", "Ooty", "Pondicherry", "Madurai", "Coorg", "Goa"]
THINGS = ["train tickets", "the hotel booking", "birthday cake", "the wedding hall", "exam results", "new phone"]


def invented_evidence(rng: random.Random) -> str:
    """A believable <evidence> block that is different on every call."""
    blocks = []
    for number in range(1, EVIDENCE_MEMORIES + 1):
        person, place, thing = rng.choice(PEOPLE), rng.choice(PLACES), rng.choice(THINGS)
        day, hour = rng.randint(1, 28), rng.randint(8, 23)
        text = (f"{person} said the {thing} for the {place} trip is sorted, costs about {rng.randint(2, 90)}00 "
                f"rupees, and we should leave by {rng.randint(5, 11)} am on the {day}th. Reply before evening da.")
        blocks.append(f'<memory id="{number}" source="whatsapp: {person}" date="2024-0{rng.randint(1, 9)}-{day:02d} '
                      f'{hour}:15" author="{person}" lang="en">\n{text}\n</memory>')
    return "<evidence>\n" + "\n".join(blocks) + "\n</evidence>"


def answer_messages(system_prompt: str, rng: random.Random) -> list[tuple[str, str]]:
    question = f"When is the {rng.choice(PLACES)} trip with {rng.choice(PEOPLE)}?"
    return [("system", system_prompt), ("user", f"{invented_evidence(rng)}\n\nQuestion: {question}")]


async def timed_request(router: AIRouter, system_prompt: str, rng: random.Random) -> dict:
    start = time.perf_counter()
    generation = await router.generate("reasoning", answer_messages(system_prompt, rng), max_tokens=OUTPUT_TOKENS)
    return {"latency_ms": (time.perf_counter() - start) * 1000, "input_tokens": generation.usage.input_tokens,
            "cached_tokens": generation.usage.cached_input_tokens}


async def run(rounds: int, router: AIRouter) -> dict:
    rng = random.Random(42)  # the same invented evidence on every run of the benchmark
    await timed_request(router, ANSWER_SYSTEM, rng)  # prime the cache with the app's system prompt
    cold, warm = [], []
    for number in range(1, rounds + 1):
        cold.append(await timed_request(router, f"Request id: {uuid.uuid4()}\n\n{ANSWER_SYSTEM}", rng))
        warm.append(await timed_request(router, ANSWER_SYSTEM, rng))
        print(f"round {number}/{rounds}: cold {cold[-1]['latency_ms']:.0f} ms, warm {warm[-1]['latency_ms']:.0f} ms "
              f"({warm[-1]['cached_tokens']} of {warm[-1]['input_tokens']} tokens cached)")

    def summary(rows: list[dict]) -> dict:
        latencies = [r["latency_ms"] for r in rows]
        return {"latency_p50_ms": round(percentile(latencies, 50), 1),
                "latency_p95_ms": round(percentile(latencies, 95), 1),
                "avg_input_tokens": round(sum(r["input_tokens"] for r in rows) / len(rows)),
                "avg_cached_tokens": round(sum(r["cached_tokens"] for r in rows) / len(rows)),
                "cache_hit_rounds": sum(r["cached_tokens"] > 0 for r in rows)}

    cold_summary, warm_summary = summary(cold), summary(warm)
    reduction = 1 - warm_summary["latency_p50_ms"] / cold_summary["latency_p50_ms"]
    return {"rounds": rounds, "cold": cold_summary, "warm": warm_summary,
            "median_latency_reduction": round(reduction, 4), "settings": run_settings(),
            "details": {"cold": cold, "warm": warm}}


def render_markdown(result: dict) -> str:
    rows = [[name, f"{s['latency_p50_ms']:.0f}", f"{s['latency_p95_ms']:.0f}", s["avg_input_tokens"],
             s["avg_cached_tokens"], f"{s['cache_hit_rounds']}/{result['rounds']}"]
            for name, s in (("cold (no cache)", result["cold"]), ("warm (system prompt cached)", result["warm"]))]
    return "\n".join([
        "# Prompt caching benchmark — answer step", "",
        f"{result['rounds']} rounds, model `{result['settings']['answer_model']}`, {OUTPUT_TOKENS} output tokens.", "",
        markdown_table(["request", "p50 ms", "p95 ms", "input tokens", "cached tokens", "cache hits"], rows), "",
        f"Median latency change with caching: **{-result['median_latency_reduction'] * 100:+.1f}%** "
        "(negative = faster).", ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    result = asyncio.run(run(args.rounds, get_router()))
    markdown = render_markdown(result)
    print(markdown)
    markdown_path, json_path = write_report("prompt-cache", markdown, result)
    print(f"saved {markdown_path} and {json_path}")


if __name__ == "__main__":
    main()
