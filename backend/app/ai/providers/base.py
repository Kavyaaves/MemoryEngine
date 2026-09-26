"""The common interface every AI provider implements (PLAN §22).

The rest of the app never calls OpenAI directly: it asks the router for a *task*, and the
router picks a provider. Provider SDK code lives only in this package.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]
Message = tuple[Role, str]  # e.g. ("user", "When did we go to Kerala?")
T = TypeVar("T", bound=BaseModel)  # a Pydantic schema for structured output

# What the app wants done. The router maps each task to an ordered list of providers.
#   reasoning  – write the final answer        fast      – quick checks, reranking
#   extraction – structured data from text     rewrite   – understand/rewrite a question
#   vision     – describe a photo              embedding – text → vector
#   speech     – audio → transcript
# "teacher" and "derived" belong to the fine-tuning phase (app/finetuning/).
Task = Literal["reasoning", "fast", "extraction", "rewrite", "vision", "embedding", "speech",
               "teacher", "derived"]


class ProviderError(Exception):
    """Any provider failure. `retryable` marks transient errors worth a retry/fallback."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class QuotaExceeded(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class AIUnavailable(Exception):
    """Every provider in the chain failed or is unconfigured — callers must degrade gracefully."""


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    # How many of the input tokens the provider served from its prompt cache (part of input_tokens).
    # OpenAI caches the start of a prompt automatically once it is 1,024+ tokens long; cached
    # tokens are cheaper and faster to process. See ai/prompts/ for how prompts are ordered for it.
    cached_input_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens,
                          self.cached_input_tokens + other.cached_input_tokens)


# Streaming calls report token usage only at the end, through this callback.
UsageCallback = Callable[[TokenUsage], None]


@dataclass
class Generation:
    text: str
    provider: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class Transcript:
    text: str
    language: str | None
    segments: list[dict]  # [{start, end, text}]
    provider: str
    model: str


class AIProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    def model_for(self, task: Task) -> str: ...

    async def generate(self, task: Task, messages: Sequence[Message], *, temperature: float = 0.2,
                       max_tokens: int | None = None) -> Generation: ...

    def stream(self, task: Task, messages: Sequence[Message], *, temperature: float = 0.2,
               on_usage: UsageCallback | None = None) -> AsyncIterator[str]: ...

    async def structured(self, task: Task, schema: type[T], messages: Sequence[Message]) -> tuple[T, TokenUsage]: ...

    async def embed(self, texts: Sequence[str], *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]: ...

    async def vision(self, image: bytes, mime_type: str, prompt: str, schema: type[T]) -> tuple[T, TokenUsage]: ...

    async def transcribe(self, audio: bytes, filename: str) -> Transcript: ...


def classify_exception(exc: Exception) -> ProviderError:
    """Map SDK exceptions to ProviderError without importing every SDK's exception types."""
    if isinstance(exc, ProviderError):
        return exc
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    if "429" in lowered or "resource_exhausted" in lowered or "rate limit" in lowered or "quota" in lowered:
        return QuotaExceeded(text)
    # Not worth retrying: bad key, bad request, or a model that doesn't exist (e.g. retired).
    permanent = ("401", "403", "permission", "api key", "invalid_argument", "400", "404", "not_found",
                 "no longer available")
    if any(s in lowered for s in permanent):
        return ProviderError(text, retryable=False)
    return ProviderError(text, retryable=True)
