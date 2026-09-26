"""The skills the derived model is trained on. One module (or package) per task.

A task provides:

    NAME            its name on the command line, e.g. "address_tagger"
    SYSTEM_PROMPT   the prompt used when labelling, training AND using it (must be identical)
    APPLY_OPTIONS   extra command-line options for `apply`, e.g. {"--person": "help text"}
    label(...)      the teacher labels examples → data/finetuning/<NAME>/labels.jsonl
    evaluate(...)   the derived model vs the task's no-AI baseline, on the validation examples
    apply(...)      put the derived model to work for this task

To add a skill: write the module, then add it to TASKS below. The next `build` + `train`
teaches it to the derived model, together with every skill it already has.
"""

from app.finetuning.tasks import address_tagger

TASKS = {task.NAME: task for task in (address_tagger,)}
