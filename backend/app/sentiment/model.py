"""The TamilSense model (vishnuexe/TamilSense-model on Hugging Face), loaded once and kept in memory.

    classify(["Super da machan!", "mood off da", "ok da"])
      → [Sentiment("positive", 0.99), Sentiment("negative", 0.97), Sentiment("neutral", 0.61)]

It is Google's MuRIL (a BERT model for Indian languages) fine-tuned on Tamil and Tanglish text.
It only knows two labels, positive and negative. When it isn't confident either way (score below
SENTIMENT_NEUTRAL_BELOW) we call the text "neutral" — "ok da" is neither happy nor sad.

The first load downloads the model (about 1 GB) into the Hugging Face cache (~/.cache/huggingface);
after that it loads from disk in a few seconds. It runs on the CPU.
"""

import logging
import threading
from dataclasses import dataclass

from app.config import get_settings

log = logging.getLogger(__name__)
MAX_TOKENS = 512  # BERT models read at most 512 tokens; longer texts are cut (truncation=True)
# Models without label names in their config report LABEL_0 / LABEL_1; TamilSense uses 0 = positive, 1 = negative.
LABEL_NAMES = {"label_0": "positive", "label_1": "negative"}


class SentimentUnavailable(Exception):
    """transformers/torch are not installed, or the model could not be loaded."""


@dataclass
class Sentiment:
    label: str  # positive | negative | neutral
    score: float  # the model's confidence in its answer, 0.5..1


_classifier = None
_lock = threading.Lock()  # two threads asking at once must not load the model twice


def _get_classifier():
    """The Hugging Face pipeline, created on first use."""
    global _classifier
    with _lock:
        if _classifier is None:
            try:
                # Imported here, not at the top: the rest of the app works without these big libraries.
                from transformers import pipeline
            except ImportError as exc:
                raise SentimentUnavailable('transformers is not installed: pip install -e ".[sentiment]"') from exc
            model_name = get_settings().sentiment_model
            log.info("loading sentiment model %s (the first time this downloads about 1 GB)", model_name)
            try:
                _classifier = pipeline("text-classification", model=model_name, device=-1)  # -1 = CPU
            except Exception as exc:  # no internet on the first run, disk full, a broken download…
                raise SentimentUnavailable(f"could not load {model_name}: {exc}") from exc
    return _classifier


def to_sentiment(output: dict, neutral_below: float) -> Sentiment:
    """One raw model answer ({"label": "positive", "score": 0.99}) → our Sentiment."""
    label = output["label"].lower()
    label = LABEL_NAMES.get(label, label)
    score = round(float(output["score"]), 4)
    return Sentiment("neutral" if score < neutral_below else label, score)


def classify(texts: list[str]) -> list[Sentiment]:
    """One Sentiment per text, in the same order.

    This is slow, blocking CPU work: from async code call it with asyncio.to_thread(classify, texts).
    """
    if not texts:
        return []
    settings = get_settings()
    outputs = _get_classifier()(texts, batch_size=settings.sentiment_batch_size, truncation=True, max_length=MAX_TOKENS)
    return [to_sentiment(output, settings.sentiment_neutral_below) for output in outputs]
