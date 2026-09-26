"""apply: the derived model tags every message in your private chats.

Each message gets its tags stored next to it, together with the derived model that made them:

    memories.meta["address_tags"] = {"model": "ft:gpt-4.1-nano-…:derived:…", "words": ["kutta", "da"]}

Asking "how do I call Nihal?" then only counts stored tags (retrieval/address.py) — no model
call per question. Tagging happens once, here, in windows of 25 messages per request.

Safe to stop and re-run: only messages not yet tagged by the CURRENT derived model are sent.
After a new derived model is trained, run it again and the new model re-tags everything.
Run it again after importing new chats, too.

Limits: it goes through the router, so the daily request quota and token budget apply
(MAX_DAILY_REQUESTS, MAX_TOKENS_PER_WINDOW). A big chat can take more than one day's
budget: it stops cleanly, and the next run continues where it stopped.
"""

import asyncio
from collections.abc import Callable

from sqlalchemy import func, literal, update
from sqlalchemy.dialects.postgresql import JSONB

from app.ai.prompts import ADDRESS_TAGGER_SYSTEM
from app.ai.providers.base import AIUnavailable
from app.ai.providers.router import get_router
from app.db.session import SessionLocal
from app.finetuning import derived_model
from app.finetuning.tasks.address_tagger.labelling import clean_tags, tags_by_number
from app.finetuning.tasks.address_tagger.windows import (
    WINDOW_SIZE,
    ChatMessage,
    count_messages,
    find_user,
    format_window,
    private_chats,
    read_messages,
)
from app.models import Memory
from app.multilingual.normalization import normalize
from app.schemas.ai import AddressTags

PARALLEL_REQUESTS = 8


async def _tag_window(router, window: list[ChatMessage], user_id) -> dict[int, set[str]]:
    tags = await router.structured("derived", AddressTags, [
        ("system", ADDRESS_TAGGER_SYSTEM), ("user", format_window(window))], user_id=user_id)
    return tags_by_number(clean_tags(tags, len(window)))


async def _save_tags(session, model: str, window: list[ChatMessage], found: dict[int, set[str]]) -> None:
    """Every message in the window is saved — also those with no address words (an empty list),
    so they count as tagged and aren't sent again."""
    for number, message in enumerate(window, start=1):
        value = {"address_tags": {"model": model, "words": sorted(found.get(number, set()))}}
        # meta = meta || {"address_tags": …}  (JSONB merge: the other keys in meta stay as they are).
        # literal(dict, JSONB) sends the dict as JSON once — json.dumps + CAST would send a JSON *string*.
        await session.execute(update(Memory).where(Memory.id == message.memory_id).values(
            meta=func.coalesce(Memory.meta, literal({}, JSONB)).op("||")(literal(value, JSONB))))


async def apply(person: str | None = None, user_email: str | None = None,
                progress: Callable[[str], None] = print) -> int:
    """Tag the private chats (all, or only the one with `person`). Returns how many messages were tagged."""
    model = derived_model()
    if not model:
        raise SystemExit("FINETUNE_DERIVED_MODEL is not set to a derived (ft:...) model - see `status`")
    router = get_router()
    tagged = 0
    async with SessionLocal() as session:
        user_id = await find_user(session, user_email)
        chats = await private_chats(session, user_id)
        if person:
            chats = [c for c in chats if normalize(person) in normalize(c.other_name)]
            if not chats:
                raise SystemExit(f"no private chat with '{person}'")

        for chat in chats:
            remaining = await count_messages(session, chat, user_id, untagged_by=model)
            progress(f"{chat.other_name}: {remaining} messages to tag with {model}")
            while remaining > 0:
                # The next untagged messages, split into windows that are tagged in parallel.
                messages = await read_messages(session, chat, user_id, limit=WINDOW_SIZE * PARALLEL_REQUESTS,
                                               untagged_by=model)
                if not messages:
                    break
                windows = [messages[i:i + WINDOW_SIZE] for i in range(0, len(messages), WINDOW_SIZE)]
                try:
                    results = await asyncio.gather(*(_tag_window(router, w, user_id) for w in windows))
                except AIUnavailable as exc:
                    progress(f"stopping: {str(exc)[:200]}\n{tagged} messages tagged so far - run `apply address_tagger` again "
                             "later (e.g. tomorrow, when the daily quota resets) to continue.")
                    return tagged
                for window, found in zip(windows, results, strict=True):
                    await _save_tags(session, model, window, found)
                await session.commit()  # saved after every round: stopping loses at most one round
                tagged += len(messages)
                remaining -= len(messages)
                progress(f"  {chat.other_name}: {max(remaining, 0)} left")
    progress(f"done: {tagged} messages tagged by {model}")
    return tagged
