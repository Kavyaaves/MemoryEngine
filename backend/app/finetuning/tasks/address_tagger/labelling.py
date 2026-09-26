"""label: the teacher model (gpt-4.1) labels random windows of your private chats.

This is "distillation": the small derived model learns to copy the big model's judgement, at a
fraction of its price per message. → data/finetuning/address_tagger/labels.jsonl, one window per
line. You can open it and fix labels by hand before `build`: better labels make a better model.
"""

import asyncio
import random
from collections.abc import Callable

from app.ai.prompts import ADDRESS_TAGGER_SYSTEM
from app.ai.providers.router import get_router
from app.db.session import SessionLocal
from app.finetuning.data import labels_file, write_labels
from app.finetuning.tasks.address_tagger.windows import (
    WINDOW_SIZE,
    count_messages,
    find_user,
    format_window,
    private_chats,
    read_messages,
)
from app.multilingual.normalization import normalize
from app.schemas.ai import AddressTags

TASK_NAME = "address_tagger"
PARALLEL_REQUESTS = 8


def clean_tags(tags: AddressTags, message_count: int) -> AddressTags:
    """Drop numbers that aren't in the window and empty word lists; keep each word once."""
    by_number: dict[int, list[str]] = {}
    for tagged in tags.messages:
        if not 1 <= tagged.id <= message_count:
            continue
        for word in (w.strip() for w in tagged.address_words):
            kept = by_number.setdefault(tagged.id, [])
            if word and word not in kept:
                kept.append(word)
    by_number = {number: kept for number, kept in by_number.items() if kept}
    return AddressTags(messages=[{"id": n, "address_words": ws} for n, ws in sorted(by_number.items())])


def tags_by_number(tags: AddressTags) -> dict[int, set[str]]:
    """{message number: {normalised address words}} — for comparing and storing tags."""
    return {t.id: {normalize(w) for w in t.address_words} for t in tags.messages}


async def label(windows: int = 80, user_email: str | None = None, overwrite: bool = False, seed: int = 7,
                progress: Callable[[str], None] = print) -> int:
    """Label `windows` random chat windows with the teacher model. Returns how many were written."""
    if labels_file(TASK_NAME).exists() and not overwrite:
        raise SystemExit(f"{labels_file(TASK_NAME)} already exists (it may hold your hand-made corrections). "
                         "Pass --overwrite to replace it.")
    router = get_router()
    if not router.available("teacher"):
        raise SystemExit("OPENAI_API_KEY is not set")

    # Pick the windows first (database), then label them (OpenAI).
    rng = random.Random(seed)  # the same seed picks the same windows again
    records = []
    async with SessionLocal() as session:
        user_id = await find_user(session, user_email)
        chats = await private_chats(session, user_id)
        sizes = [await count_messages(session, chat, user_id) for chat in chats]
        if not chats or not any(sizes):
            raise SystemExit("no private chats found - import a WhatsApp chat first")
        progress(f"{len(chats)} private chats, {sum(sizes)} messages")
        for _ in range(windows):
            chat_index = rng.choices(range(len(chats)), weights=sizes)[0]  # bigger chats get more windows
            chat = chats[chat_index]
            offset = rng.randrange(max(1, sizes[chat_index] - WINDOW_SIZE))
            messages = await read_messages(session, chat, user_id, offset=offset)
            records.append({"person": chat.other_name, "names": [chat.self_name, chat.other_name],
                            "memory_ids": [str(m.memory_id) for m in messages],
                            "texts": [m.text for m in messages], "input": format_window(messages)})

    teacher = router.providers["openai"].model_for("teacher")
    progress(f"labelling {len(records)} windows ({len(records) * WINDOW_SIZE} messages) with {teacher} ...")

    async def label_one(record: dict) -> None:
        tags = await router.structured("teacher", AddressTags, [
            ("system", ADDRESS_TAGGER_SYSTEM), ("user", record["input"])], user_id=user_id)
        record["output"] = clean_tags(tags, len(record["memory_ids"])).model_dump()

    for start in range(0, len(records), PARALLEL_REQUESTS):
        await asyncio.gather(*(label_one(r) for r in records[start:start + PARALLEL_REQUESTS]))
        progress(f"  {min(start + PARALLEL_REQUESTS, len(records))}/{len(records)} labelled")

    path = write_labels(TASK_NAME, records)
    tagged = sum(len(r["output"]["messages"]) for r in records)
    progress(f"wrote {path} - {tagged} messages have address words. Check a few, then run `build`.")
    return len(records)
