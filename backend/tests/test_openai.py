"""The OpenAI provider against a fake OpenAI server (httpx.MockTransport): no key or network needed.

Chat goes through LangChain's ChatOpenAI and the rest through the openai SDK; both send their
HTTP requests to the fake server.
"""

import base64
import json
import struct

import httpx
import pytest

from app.ai.providers.base import ProviderError, QuotaExceeded, TokenUsage
from app.ai.providers.openai import (
    MAX_EMBEDDING_INPUT_BYTES,
    MAX_EMBEDDING_REQUEST_BYTES,
    OpenAIProvider,
    embedding_batches,
    sampling_options,
    truncate_utf8,
)
from app.config import Settings
from app.schemas.ai import EvidenceVerdict


def provider_with(handler) -> OpenAIProvider:
    """A provider whose HTTP requests go to `handler` instead of api.openai.com."""
    return OpenAIProvider(Settings(openai_api_key="sk-test"), max_retries=0,
                          http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def embeddings_reply(request: httpx.Request) -> httpx.Response:
    """Like OpenAI: one vector per input (here filled with the input's length), in the format asked for."""
    body = json.loads(request.content)
    data = []
    for index, text in enumerate(body["input"]):
        vector = [float(len(text))] * body["dimensions"]
        if body.get("encoding_format") == "base64":  # the SDK asks for this by default: smaller replies
            vector = base64.b64encode(struct.pack(f"{len(vector)}f", *vector)).decode()
        data.append({"object": "embedding", "index": index, "embedding": vector})
    data.reverse()  # the order isn't guaranteed; the provider sorts by index
    return httpx.Response(200, json={"object": "list", "data": data, "model": body["model"],
                                     "usage": {"prompt_tokens": 1, "total_tokens": 1}})


def chat_reply(content: str, cached_tokens: int = 0) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4.1-nano",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content, "refusal": None}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19,
                  "prompt_tokens_details": {"cached_tokens": cached_tokens}}})


async def test_embeddings_have_768_dimensions_and_keep_the_input_order():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return embeddings_reply(request)

    vectors = await provider_with(handler).embed(["a", "bbb"])
    assert requests[0]["model"] == "text-embedding-3-small" and requests[0]["dimensions"] == 768
    assert len(vectors[0]) == 768
    assert [vector[0] for vector in vectors] == [1.0, 3.0]


def test_long_texts_and_big_batches_are_cut_to_fit_openai_limits():
    tamil = "த" * 5000  # 3 bytes of UTF-8 per letter
    assert truncate_utf8(tamil) == "த" * (MAX_EMBEDDING_INPUT_BYTES // 3)  # cut on a letter boundary
    batches = embedding_batches(["x" * 8000] * 100)
    assert sum(len(batch) for batch in batches) == 100
    assert all(sum(len(text) for text in batch) <= MAX_EMBEDDING_REQUEST_BYTES for batch in batches)


def test_reasoning_models_are_sent_no_temperature():
    assert sampling_options("gpt-4.1-mini", 0.2) == {"temperature": 0.2}
    assert sampling_options("gpt-5-mini", 0.2, max_tokens=100) == {"max_completion_tokens": 100}


async def test_structured_output_is_parsed_into_the_schema():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return chat_reply('{"sufficient": true, "confidence": "high", "alternative_queries": []}')

    verdict, usage = await provider_with(handler).structured("fast", EvidenceVerdict, [("user", "enough?")])
    assert verdict == EvidenceVerdict(sufficient=True, confidence="high")
    assert (usage.input_tokens, usage.output_tokens) == (12, 7)
    assert requests[0]["model"] == "gpt-4.1-nano"  # quick checks use the fast model
    assert requests[0]["response_format"]["type"] == "json_schema"


async def test_every_chat_request_carries_a_prompt_cache_key_and_reports_cached_tokens():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return chat_reply("hello", cached_tokens=1024)

    generation = await provider_with(handler).generate("reasoning", [("system", "rules"), ("user", "hi")])
    assert requests[0]["prompt_cache_key"] == "memory-engine:reasoning"
    assert requests[0]["model"] == "gpt-4.1-mini" and requests[0]["temperature"] == 0.2
    assert generation.text == "hello"
    assert generation.usage == TokenUsage(input_tokens=12, output_tokens=7, cached_input_tokens=1024)


async def test_streamed_answer_arrives_in_pieces_and_reports_usage_at_the_end():
    pieces = ["You planned ", "it [1]."]
    events = [{"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "gpt-4.1-mini",
               "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]} for piece in pieces]
    # With stream_options.include_usage, OpenAI sends one last chunk with no choices, only usage.
    events.append({"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "gpt-4.1-mini",
                   "choices": [], "usage": {"prompt_tokens": 1500, "completion_tokens": 9, "total_tokens": 1509,
                                            "prompt_tokens_details": {"cached_tokens": 1280}}})
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    reported = []
    provider = provider_with(handler)
    assert [piece async for piece in provider.stream("reasoning", [("user", "hi")], on_usage=reported.append)] == pieces
    assert requests[0]["stream_options"] == {"include_usage": True}
    assert reported == [TokenUsage(input_tokens=1500, output_tokens=9, cached_input_tokens=1280)]


async def test_bad_key_is_not_retried_and_rate_limits_move_on_to_the_next_provider():
    wrong_key = provider_with(lambda request: httpx.Response(401, json={"error": {
        "message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}}))
    with pytest.raises(ProviderError) as error:
        await wrong_key.generate("reasoning", [("user", "hi")])
    assert error.value.retryable is False

    rate_limited = provider_with(lambda request: httpx.Response(429, json={"error": {
        "message": "Rate limit reached", "type": "requests", "code": "rate_limit_exceeded"}}))
    with pytest.raises(QuotaExceeded):
        await rate_limited.generate("reasoning", [("user", "hi")])
