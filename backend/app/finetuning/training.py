"""Training: one lineage, base → derived v1 → derived v2 → …

    train   uploads train.jsonl + val.jsonl and starts a fine-tuning job. It starts from the
            CURRENT DERIVED MODEL (FINETUNE_DERIVED_MODEL), so the model keeps what it learned
            before; only the very first run starts from the base model (FINETUNE_BASE_MODEL).
    status  asks OpenAI how the job is doing (minutes to an hour or so). When it has finished,
            it prints the new derived model, e.g.
                FINETUNE_DERIVED_MODEL=ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123
            Put that line in backend/.env and restart the API: the app now uses the new model.

lineage.json records every run: which model it started from, the model it produced, and the
tasks it was trained on — the model's family tree.

Training runs on OpenAI's servers (no local models, PLAN §21). OpenAI bills it per training
token (examples × epochs): check https://openai.com/api/pricing before starting. These calls
use the OpenAI SDK directly — file uploads and jobs, not chat requests — so the router's quota
doesn't apply to them.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime

from app.ai.providers.openai import OpenAIProvider
from app.config import get_settings
from app.finetuning import base_model, derived_model
from app.finetuning.data import DATA_DIR, TRAIN_FILE, VAL_FILE, labels_file

LINEAGE_FILE = DATA_DIR / "lineage.json"
TRAINING_SUFFIX = "derived"  # becomes part of the model's name: ft:…:derived:…


def _client():
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set")
    return OpenAIProvider(settings).client


def _line_count(path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_lineage() -> dict:
    if LINEAGE_FILE.exists():
        return json.loads(LINEAGE_FILE.read_text(encoding="utf-8"))
    return {"base_model": base_model(), "runs": []}


def _save_lineage(lineage: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LINEAGE_FILE.write_text(json.dumps(lineage, indent=2), encoding="utf-8")


def starting_model() -> str:
    """Where the next training run starts: the current derived model, or the base the first time."""
    return derived_model() or base_model()


async def start_training(tasks: dict, progress: Callable[[str], None] = print) -> str:
    """Upload the files and start the job. Returns the job id."""
    for path in (TRAIN_FILE, VAL_FILE):
        if not path.exists():
            raise SystemExit(f"{path} not found - run `build` first")
    lineage = read_lineage()
    if lineage["runs"] and lineage["runs"][-1].get("status") not in ("succeeded", "failed", "cancelled"):
        raise SystemExit(f"job {lineage['runs'][-1]['job_id']} is still running - check it with `status`")

    start_from = starting_model()
    client = _client()
    with TRAIN_FILE.open("rb") as file:
        train_file = await client.files.create(file=file, purpose="fine-tune")
    with VAL_FILE.open("rb") as file:
        val_file = await client.files.create(file=file, purpose="fine-tune")
    job = await client.fine_tuning.jobs.create(
        model=start_from, training_file=train_file.id, validation_file=val_file.id,
        suffix=TRAINING_SUFFIX, seed=42)  # a fixed seed makes a re-run train the same way

    lineage["runs"].append({
        "job_id": job.id, "status": job.status, "started_from": start_from, "derived_model": None,
        "tasks": [name for name in tasks if labels_file(name).exists()],
        "training_examples": _line_count(TRAIN_FILE), "validation_examples": _line_count(VAL_FILE),
        "started_at": datetime.now(UTC).isoformat(),
    })
    _save_lineage(lineage)
    label = "the current derived model" if start_from != base_model() else "the base model"
    progress(f"started job {job.id} from {label} {start_from}. Check it with `status`.")
    return job.id


async def check_status(progress: Callable[[str], None] = print) -> str | None:
    """Print the latest job's state. Returns the new derived model once it exists."""
    lineage = read_lineage()
    if not lineage["runs"]:
        raise SystemExit("no training run yet - run `train` first")
    run = lineage["runs"][-1]
    client = _client()
    job = await client.fine_tuning.jobs.retrieve(run["job_id"])
    events = await client.fine_tuning.jobs.list_events(run["job_id"], limit=5)

    run["status"] = job.status
    run["derived_model"] = job.fine_tuned_model
    if job.trained_tokens:
        run["trained_tokens"] = job.trained_tokens
    _save_lineage(lineage)

    progress(f"base model:     {lineage['base_model']}")
    progress(f"started from:   {run['started_from']}")
    progress(f"job {job.id}: {job.status}")
    for event in reversed(events.data):  # oldest first
        progress(f"  {datetime.fromtimestamp(event.created_at, UTC):%H:%M} {event.message}")
    if job.status == "failed" and job.error:
        progress(f"  error: {job.error.message}")
    if job.fine_tuned_model:
        progress(f"derived model:  {job.fine_tuned_model}")
        progress("\nTrained. Put this line in backend/.env, restart the API, then `evaluate` and `apply` each task:")
        progress(f"FINETUNE_DERIVED_MODEL={job.fine_tuned_model}")
    return job.fine_tuned_model
