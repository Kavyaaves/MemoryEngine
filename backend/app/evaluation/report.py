"""Writing evaluation results: a Markdown report to read, and a JSON file with every number.

Both go to eval/results/<date>-<time>-<name>.md / .json, so runs never overwrite each other and
a before/after comparison is two files side by side.
"""

import json
from datetime import datetime
from pathlib import Path

from app.ai.prompts import PROMPT_VERSION
from app.config import get_settings

RESULTS_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"  # backend/eval/results


def markdown_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def run_settings() -> dict:
    """What produced the numbers — saved with every report, so old results stay interpretable."""
    s = get_settings()
    return {"prompt_version": PROMPT_VERSION, "answer_model": s.openai_reasoning_model,
            "fast_model": s.openai_fast_model, "embedding_model": s.embedding_model,
            "top_k": s.retrieval_top_k, "rrf_k": s.rrf_k}


def write_report(name: str, markdown: str, data: dict, results_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y-%m-%d-%H%M%S}-{name}"
    markdown_path, json_path = results_dir / f"{stem}.md", results_dir / f"{stem}.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return markdown_path, json_path
