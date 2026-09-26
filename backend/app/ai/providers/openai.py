"""OpenAI: the AI provider — answers, quick checks, photo descriptions, transcripts and embeddings.

- Chat (answers, quick checks, structured output) goes through LangChain's ChatOpenAI.
- Embeddings, vision and transcription call the official `openai` SDK directly: our embedding
  batching already follows OpenAI's limits, and LangChain's chat interface has no audio upload.
Every error is converted to a ProviderError, so the router can decide whether to retry.

Prompt caching: OpenAI automatically caches the start of any prompt that is 1,024+ tokens long,
so a later request that starts with the same text is processed faster and billed less for it.
Each chat request also sends a `prompt_cache_key` (one per task), which routes requests that
share a prefix to the same servers and so raises the cache hit rate. How many input tokens were
served from the cache is reported in TokenUsage.cached_input_tokens (and saved to ai_usage).
"""

import base64
from collections.abc import AsyncIterator, Sequence

import httpx
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.ai.providers.base import (
    Generation,
    Message,
    ProviderError,
    T,
    Task,
    TokenUsage,
    Transcript,
    classify_exception,
)
from app.ai.providers.langchain_utils import response_text, stream_text, to_langchain_messages, token_usage
from app.config import Settings

# Reasoning models (gpt-5, o-series) accept only their default temperature, so none is sent to them.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# OpenAI's embedding models read at most 8,192 tokens per text. A token is at least one byte of
# UTF-8, so 8,000 bytes always fit — whatever the script (a Tamil letter is 3 bytes, and may be a token).
MAX_EMBEDDING_INPUT_BYTES = 8000
# One embeddings request may hold at most 2,048 texts and 300,000 tokens; bytes bound the tokens again.
MAX_EMBEDDING_REQUEST_TEXTS = 2048
MAX_EMBEDDING_REQUEST_BYTES = 290_000
REQUEST_TIMEOUT_SECONDS = 60


def openai_messages(messages: Sequence[Message]) -> list[dict]:
    """[("system", "..."), ("user", "...")] → the SDK's [{"role": ..., "content": ...}]."""
    return [{"role": role, "content": content} for role, content in messages]


def sampling_options(model: str, temperature: float, max_tokens: int | None = None) -> dict:
    options: dict = {}
    if not model.startswith(REASONING_MODEL_PREFIXES):
        options["temperature"] = temperature
    if max_tokens:
        options["max_completion_tokens"] = max_tokens
    return options


def prompt_cache_key(task: Task) -> str:
    """Requests with the same key (and the same prompt start) are sent to the same cache."""
    return f"memory-engine:{task}"


def truncate_utf8(text: str, max_bytes: int = MAX_EMBEDDING_INPUT_BYTES) -> str:
    """At most `max_bytes` of UTF-8, cut on a character boundary."""
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def embedding_batches(texts: list[str]) -> list[list[str]]:
    """Split texts into requests that stay within OpenAI's per-request limits."""
    batches: list[list[str]] = [[]]
    batch_bytes = 0
    for text in texts:
        size = len(text.encode("utf-8"))
        batch = batches[-1]
        if batch and (len(batch) >= MAX_EMBEDDING_REQUEST_TEXTS or batch_bytes + size > MAX_EMBEDDING_REQUEST_BYTES):
            batches.append([])
            batch_bytes = 0
        batches[-1].append(text)
        batch_bytes += size
    return [batch for batch in batches if batch]


def sdk_token_usage(usage) -> TokenUsage:
    """Token counts from a raw SDK response (the vision call)."""
    if usage is None:
        return TokenUsage()
    details = getattr(usage, "prompt_tokens_details", None)
    return TokenUsage(input_tokens=usage.prompt_tokens or 0, output_tokens=usage.completion_tokens or 0,
                      cached_input_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0)


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None, max_retries: int = 1):
        self.settings = settings
        self._http_client = http_client  # tests pass a client with a fake transport
        # The router already retries, so the SDK itself retries only once.
        self._max_retries = max_retries
        self._client: AsyncOpenAI | None = None
        self._chat_models: dict[tuple[Task, float], ChatOpenAI] = {}

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    @property
    def client(self) -> AsyncOpenAI:
        """The raw SDK client (embeddings, vision, transcription)."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key, max_retries=self._max_retries,
                                       timeout=REQUEST_TIMEOUT_SECONDS, http_client=self._http_client)
        return self._client

    def model_for(self, task: Task) -> str:
        models = {
            "fast": self.settings.openai_fast_model,
            "rewrite": self.settings.openai_fast_model,
            "vision": self.settings.openai_vision_model,
            "speech": self.settings.openai_speech_model,
            "embedding": self.settings.openai_embedding_model,
            # fine-tuning phase: the labelling "teacher", and the derived model we trained ("ft:…")
            "teacher": self.settings.finetune_teacher_model,
            "derived": self.settings.finetune_derived_model or "",
        }
        return models.get(task, self.settings.openai_reasoning_model)  # reasoning, extraction

    def chat_model(self, task: Task, temperature: float = 0.2) -> ChatOpenAI:
        """A (cached) LangChain chat model for this task."""
        key = (task, temperature)
        if key not in self._chat_models:
            model = self.model_for(task)
            self._chat_models[key] = ChatOpenAI(
                model=model, api_key=self.settings.openai_api_key, max_retries=self._max_retries,
                timeout=REQUEST_TIMEOUT_SECONDS, http_async_client=self._http_client,
                stream_usage=True,  # streamed answers report their token counts (incl. cached) at the end
                model_kwargs={"prompt_cache_key": prompt_cache_key(task)},
                **sampling_options(model, temperature))
        return self._chat_models[key]

    async def generate(self, task, messages, *, temperature=0.2, max_tokens=None) -> Generation:
        model = self.chat_model(task, temperature)
        if max_tokens:
            model = model.bind(max_completion_tokens=max_tokens)
        try:
            reply = await model.ainvoke(to_langchain_messages(messages))
        except Exception as exc:
            raise classify_exception(exc) from exc
        return Generation(text=response_text(reply), provider=self.name, model=self.model_for(task),
                          usage=token_usage(reply))

    async def stream(self, task, messages, *, temperature=0.2, on_usage=None) -> AsyncIterator[str]:
        try:
            async for text in stream_text(self.chat_model(task, temperature), messages, on_usage):
                yield text
        except Exception as exc:
            raise classify_exception(exc) from exc

    async def structured(self, task, schema: type[T], messages) -> tuple[T, TokenUsage]:
        """Ask for JSON matching `schema` (OpenAI's structured outputs) and get a validated Pydantic object."""
        model = self.chat_model(task, temperature=0.0).with_structured_output(
            schema, method="json_schema", include_raw=True)
        try:
            out = await model.ainvoke(to_langchain_messages(messages))
        except Exception as exc:
            raise classify_exception(exc) from exc
        if out.get("parsed") is None:  # the model refused, or the answer was cut off
            raise ProviderError(f"no structured output: {out.get('parsing_error') or 'empty reply'}")
        return out["parsed"], token_usage(out.get("raw"))

    async def embed(self, texts, *, task_type="RETRIEVAL_DOCUMENT") -> list[list[float]]:
        # OpenAI embeds stored text and search queries the same way, so task_type is not sent.
        vectors: list[list[float]] = []
        for batch in embedding_batches([truncate_utf8(text) for text in texts]):
            try:
                response = await self.client.embeddings.create(
                    model=self.settings.openai_embedding_model, input=batch, dimensions=self.settings.embedding_dim)
            except Exception as exc:
                raise classify_exception(exc) from exc
            vectors += [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts):
            raise ProviderError(f"asked for {len(texts)} embeddings, got {len(vectors)}", retryable=False)
        return vectors

    async def vision(self, image: bytes, mime_type: str, prompt: str, schema: type[T]) -> tuple[T, TokenUsage]:
        model = self.settings.openai_vision_model
        image_url = f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                                 {"type": "image_url", "image_url": {"url": image_url}}]}]
        try:
            response = await self.client.chat.completions.parse(
                model=model, messages=messages, response_format=schema, **sampling_options(model, 0.0))
        except Exception as exc:
            raise classify_exception(exc) from exc
        message = response.choices[0].message
        if message.parsed is None:  # the model refused, or the answer was cut off
            raise ProviderError(f"no structured output: {message.refusal or 'empty reply'}")
        return message.parsed, sdk_token_usage(response.usage)

    async def transcribe(self, audio: bytes, filename: str) -> Transcript:
        model = self.settings.openai_speech_model
        try:
            response = await self.client.audio.transcriptions.create(model=model, file=(filename, audio))
        except Exception as exc:
            raise classify_exception(exc) from exc
        return Transcript(text=response.text or "", language=None, segments=[], provider=self.name, model=model)
