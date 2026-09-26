"""Training data, shared by every task.

Each task keeps its labelled examples in data/finetuning/<task>/labels.jsonl, one per line:

    {"input": "<what the model reads>", "output": {<the answer we want, as JSON>}, ...task-specific fields}

`build` turns the labels of ALL tasks into one pair of OpenAI training files. Training on every
task each time is what lets the one derived model learn a new skill without forgetting the old
ones. The task's system prompt goes first in each example: that's how the model knows which
job it's doing, so it must be the exact prompt the task uses later.

Every 5th example of each task goes to the validation file instead: the model never trains on
those, so they show how well it really does (`evaluate`).
"""

import json
from collections.abc import Callable
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "finetuning"  # backend/data/finetuning (git-ignored)
TRAIN_FILE = DATA_DIR / "train.jsonl"
VAL_FILE = DATA_DIR / "val.jsonl"
MIN_TRAINING_EXAMPLES = 10  # OpenAI refuses to fine-tune on fewer


def labels_file(task_name: str) -> Path:
    return DATA_DIR / task_name / "labels.jsonl"


def is_validation(index: int) -> bool:
    """Every 5th example is held out (the same split in `build` and `evaluate`)."""
    return index % 5 == 4


def read_labels(task_name: str) -> list[dict]:
    path = labels_file(task_name)
    if not path.exists():
        raise SystemExit(f"{path} not found - run `label {task_name}` first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_labels(task_name: str, records: list[dict]) -> Path:
    path = labels_file(task_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def training_example(system_prompt: str, record: dict) -> dict:
    """One line of an OpenAI fine-tuning file: the conversation we want the model to learn."""
    return {"messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": record["input"]},
        {"role": "assistant", "content": json.dumps(record["output"], ensure_ascii=False)},
    ]}


def build(tasks: dict, progress: Callable[[str], None] = print) -> tuple[int, int]:
    """Every task's labels → train.jsonl + val.jsonl. Returns (training examples, validation examples)."""
    train, val = [], []
    for name, task in tasks.items():
        if not labels_file(name).exists():
            progress(f"  {name}: no labels yet - skipped")
            continue
        records = read_labels(name)
        task_train = [training_example(task.SYSTEM_PROMPT, r) for i, r in enumerate(records) if not is_validation(i)]
        task_val = [training_example(task.SYSTEM_PROMPT, r) for i, r in enumerate(records) if is_validation(i)]
        progress(f"  {name}: {len(task_train)} training + {len(task_val)} validation examples")
        train += task_train
        val += task_val
    if len(train) < MIN_TRAINING_EXAMPLES:
        raise SystemExit(f"only {len(train)} training examples; OpenAI needs {MIN_TRAINING_EXAMPLES}+. "
                         "Label more with `label <task>`.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, examples in ((TRAIN_FILE, train), (VAL_FILE, val)):
        with path.open("w", encoding="utf-8") as file:
            for example in examples:
                file.write(json.dumps(example, ensure_ascii=False) + "\n")
    progress(f"wrote {len(train)} training and {len(val)} validation examples. Next: `train`.")
    return len(train), len(val)
