"""The fine-tuning phase (PLAN §20–21): the model this project TRAINS, as opposed to the standard
hosted models it only calls.

Two labels:

    base model     FINETUNE_BASE_MODEL, e.g. gpt-4.1-nano-2025-04-14 — a standard OpenAI model,
                   the starting point of the very first training run
    derived model  FINETUNE_DERIVED_MODEL, e.g. ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123
                   — the result of our training. There is ONE derived model: every new training
                   run starts from the current derived model (not from the base again), so it keeps
                   learning. Each run produces a new derived model, which then replaces the old one.

    base ──train──▶ derived v1 ──train──▶ derived v2 ──train──▶ …      (lineage.json keeps the history)

What the derived model learns comes from TASKS (tasks/). A task is one skill, with its own
system prompt, its own labelled data and its own way of being used. Every training run
includes the data of every task, so learning a new skill doesn't make it forget an old one.

    Task              Skill                                            Used by
    ----------------  -----------------------------------------------  ---------------------------
    address_tagger    the words used to address someone in a chat      Ask: "how do I call X?"
                      (pet names, "da"/"di", nicknames)                (retrieval/address.py)

The steps (one command each, run from backend/ — see __main__.py):

    label <task>     a big "teacher" model labels examples             → data/finetuning/<task>/labels.jsonl
    build            all tasks' labels → OpenAI training files         → data/finetuning/train.jsonl, val.jsonl
    train            start a training job from the current derived model (or the base, the first time)
    status           check the job; prints the new FINETUNE_DERIVED_MODEL=ft:… line for backend/.env
    evaluate <task>  the derived model vs the task's no-AI baseline, on held-out examples
    apply <task>     put the derived model to work (e.g. tag the stored messages)

Nothing depends on the derived model: without it, every task falls back to its baseline.
Answers that used it say so — the trace's `finetune` field and a "derived model" badge in Ask.
"""

from app.config import get_settings


def is_derived(model: str | None) -> bool:
    """True for a model trained here: OpenAI names fine-tuned models 'ft:<base model>:…'."""
    return bool(model) and model.startswith("ft:")


def base_model() -> str:
    """The standard model the lineage started from."""
    return get_settings().finetune_base_model


def derived_model() -> str | None:
    """The current derived model, or None if none has been trained (or set) yet."""
    model = get_settings().finetune_derived_model
    return model if is_derived(model) else None
