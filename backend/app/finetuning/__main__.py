"""The fine-tuning phase from the command line (run from backend/):

    python -m app.finetuning tasks                        list the tasks (skills) and the models
    python -m app.finetuning label <task> [--windows 80]  the teacher labels examples for one task
    python -m app.finetuning build                        all tasks' labels → train.jsonl + val.jsonl
    python -m app.finetuning train                        train, starting from the current derived model
    python -m app.finetuning status                       check the job; prints FINETUNE_DERIVED_MODEL=…
    python -m app.finetuning evaluate <task>              derived model vs the task's baseline
    python -m app.finetuning apply <task> [options]       put the derived model to work for a task

For example, the address tagger:  label address_tagger → build → train → status →
evaluate address_tagger → apply address_tagger --person Nihal.  See app/finetuning/__init__.py.
"""

import argparse
import asyncio
import logging

from app.finetuning import base_model, data, derived_model, training
from app.finetuning.tasks import TASKS


def show_tasks() -> None:
    print(f"base model:     {base_model()}")
    print(f"derived model:  {derived_model() or '(none trained yet - the next `train` starts from the base model)'}")
    print("tasks:")
    for name in TASKS:
        labelled = "labelled" if data.labels_file(name).exists() else "no labels yet"
        print(f"  {name:<18} {labelled}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.finetuning", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-email", help="whose data to use (only needed with several accounts)")
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser("tasks", help="list the tasks and the base / derived model")
    label = steps.add_parser("label", help="the teacher model labels examples for a task")
    label.add_argument("task", choices=TASKS)
    label.add_argument("--windows", type=int, default=80, help="how many examples to label (default 80)")
    label.add_argument("--overwrite", action="store_true", help="replace the task's existing labels")
    steps.add_parser("build", help="write train.jsonl and val.jsonl from every task's labels")
    steps.add_parser("train", help="start training from the current derived model (or the base)")
    steps.add_parser("status", help="check the training job; prints the new derived model when done")
    evaluate = steps.add_parser("evaluate", help="compare the derived model with a task's baseline")
    evaluate.add_argument("task", choices=TASKS)
    apply = steps.add_parser("apply", help="use the derived model for a task")
    apply.add_argument("task", choices=TASKS)
    for task in TASKS.values():  # each task's own options for `apply`, e.g. --person
        for flag, help_text in task.APPLY_OPTIONS.items():
            apply.add_argument(flag, help=f"{task.NAME}: {help_text}")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    if args.step == "tasks":
        show_tasks()
    elif args.step == "label":
        asyncio.run(TASKS[args.task].label(args.windows, args.user_email, args.overwrite))
    elif args.step == "build":
        data.build(TASKS)
    elif args.step == "train":
        asyncio.run(training.start_training(TASKS))
    elif args.step == "status":
        asyncio.run(training.check_status())
    elif args.step == "evaluate":
        asyncio.run(TASKS[args.task].evaluate())
    elif args.step == "apply":
        task = TASKS[args.task]
        options = {flag.lstrip("-").replace("-", "_"): getattr(args, flag.lstrip("-").replace("-", "_"))
                   for flag in task.APPLY_OPTIONS}
        asyncio.run(task.apply(user_email=args.user_email, **options))


if __name__ == "__main__":
    main()
