"""evaluate: is the derived model actually better than the word list at this task?

Both are run on the validation windows (never used for training), and compared with the
teacher's labels, word by word:

    precision  of the words it found, how many are real address words
    recall     of the real address words, how many it found
    F1         one number combining both

The word list's weak spots show up here: low recall (nicknames it doesn't know) and some wrong
hits ("da" meant for someone else). If the derived model isn't clearly better, don't `apply` it.
→ data/finetuning/address_tagger/eval.json (the base and derived model are recorded in it)
"""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

from app.ai.prompts import ADDRESS_TAGGER_SYSTEM
from app.ai.providers.router import get_router
from app.finetuning import base_model, derived_model
from app.finetuning.data import is_validation, labels_file, read_labels
from app.finetuning.tasks.address_tagger.labelling import PARALLEL_REQUESTS, TASK_NAME, clean_tags, tags_by_number
from app.multilingual.normalization import normalize, words
from app.retrieval.address import classify_word
from app.schemas.ai import AddressTags

Found = set[tuple[int, int, str]]  # (window, message number, normalised word)


def word_list_tags(texts: list[str], names: list[str]) -> dict[int, set[str]]:
    """The baseline: what the hand-written word list finds in each message."""
    name_words = {normalize(name) for name in names}
    found = {}
    for number, text in enumerate(texts, start=1):
        hits = {w for w in words(normalize(text)) if classify_word(w, name_words)}
        if hits:
            found[number] = hits
    return found


def flatten(window: int, tags: dict[int, set[str]]) -> Found:
    return {(window, number, word) for number, found in tags.items() for word in found}


def scores(predicted: Found, gold: Found) -> dict[str, float]:
    right = len(predicted & gold)
    precision = right / len(predicted) if predicted else 0.0
    recall = right / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


async def evaluate(progress: Callable[[str], None] = print) -> dict:
    model = derived_model()
    if not model:
        raise SystemExit("FINETUNE_DERIVED_MODEL is not set to a derived (ft:...) model - see `status`")
    router = get_router()
    records = [r for i, r in enumerate(read_labels(TASK_NAME)) if is_validation(i)]
    progress(f"evaluating derived model {model} on {len(records)} validation windows ...")

    async def derived_tags(record: dict) -> dict[int, set[str]]:
        tags = await router.structured("derived", AddressTags, [
            ("system", ADDRESS_TAGGER_SYSTEM), ("user", record["input"])])
        return tags_by_number(clean_tags(tags, len(record["memory_ids"])))

    predictions: list[dict[int, set[str]]] = []
    for start in range(0, len(records), PARALLEL_REQUESTS):
        predictions += await asyncio.gather(*(derived_tags(r) for r in records[start:start + PARALLEL_REQUESTS]))

    gold, baseline, derived = set(), set(), set()
    for window, (record, predicted) in enumerate(zip(records, predictions, strict=True)):
        gold |= flatten(window, tags_by_number(AddressTags.model_validate(record["output"])))
        baseline |= flatten(window, word_list_tags(record["texts"], record["names"]))
        derived |= flatten(window, predicted)

    report = {
        "task": TASK_NAME, "base_model": base_model(), "derived_model": model,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "validation_windows": len(records), "labelled_address_words": len(gold),
        "word_list": scores(baseline, gold), "derived": scores(derived, gold),
        "missed_by_word_list_found_by_derived": sorted({w for _, _, w in (gold & derived) - baseline})[:30],
    }
    eval_file = labels_file(TASK_NAME).parent / "eval.json"
    eval_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    progress(f"\n{'':<12}{'precision':>10}{'recall':>8}{'F1':>7}")
    for name in ("word_list", "derived"):
        s = report[name]
        progress(f"{name:<12}{s['precision']:>10}{s['recall']:>8}{s['f1']:>7}")
    progress(f"\nfound only by the derived model: {', '.join(report['missed_by_word_list_found_by_derived']) or '-'}")
    progress(f"saved {eval_file}")
    return report
