"""Task: ADDRESS TAGGER (PLAN §20 F) — one of the skills the derived model is trained on.

The job: in a private chat, find the words used to address the other person —
    "[1] Kavya: Illa kutta, naliku pesalam da"   →   [1]: ["kutta", "da"]
Ask's "how do I call Nihal?" then counts them (retrieval/address.py).

Why train for it: the baseline, a hand-written word list (multilingual/lexicon.py ADDRESS_TERMS),
can't read context. It can't tell "panni" (piggy) from "panni vechen" (did it), and it never finds
a nickname nobody wrote into the list.

    label     windows.py + labelling.py  the teacher labels ~2,000 messages from your private chats
    evaluate  evaluation.py              derived model vs the word list, on the validation windows
    apply     tagging.py                 the derived model tags every message in your private chats;
                                         the tags are stored in memories.meta["address_tags"],
                                         together with the derived model that made them

When the derived model is retrained, its new version tags the messages again (`apply` sends
only messages not yet tagged by the current derived model). Until then, counting uses the
word list for untagged messages.
"""

from app.ai.prompts import ADDRESS_TAGGER_SYSTEM
from app.finetuning.tasks.address_tagger.evaluation import evaluate
from app.finetuning.tasks.address_tagger.labelling import label
from app.finetuning.tasks.address_tagger.tagging import apply

NAME = "address_tagger"
SYSTEM_PROMPT = ADDRESS_TAGGER_SYSTEM
APPLY_OPTIONS = {"--person": "only the private chat with this person"}

__all__ = ["APPLY_OPTIONS", "NAME", "SYSTEM_PROMPT", "apply", "evaluate", "label"]
