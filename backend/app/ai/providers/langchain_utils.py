"""Small adapters between our simple message format and LangChain chat models.

Chat goes through LangChain (see openai.py), so any LangChain chat model can plug in with the
same message format, streaming loop and token-usage format (`usage_metadata`).
"""

from collections.abc import AsyncIterator, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.ai.providers.base import Message, TokenUsage, UsageCallback

_MESSAGE_CLASSES = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def to_langchain_messages(messages: Sequence[Message]) -> list[BaseMessage]:
    """[("system", "..."), ("user", "...")] → LangChain message objects."""
    return [_MESSAGE_CLASSES[role](content=content) for role, content in messages]


def response_text(message) -> str:
    """Text of a LangChain response. Content may be a string or a list of content blocks."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)


def token_usage(message) -> TokenUsage:
    """LangChain's usage_metadata → TokenUsage. `cache_read` = input tokens served from the prompt cache."""
    usage = getattr(message, "usage_metadata", None) or {}
    details = usage.get("input_token_details") or {}
    return TokenUsage(input_tokens=usage.get("input_tokens", 0) or 0,
                      output_tokens=usage.get("output_tokens", 0) or 0,
                      cached_input_tokens=details.get("cache_read", 0) or 0)


async def stream_text(model: BaseChatModel, messages: Sequence[Message],
                      on_usage: UsageCallback | None = None) -> AsyncIterator[str]:
    """Yield the reply's text as it arrives; report the token usage once the stream ends.

    Providers put usage on one or more chunks (OpenAI: only the last one), so the counts
    are added up across all chunks.
    """
    usage = TokenUsage()
    async for chunk in model.astream(to_langchain_messages(messages)):
        if getattr(chunk, "usage_metadata", None):
            usage += token_usage(chunk)
        text = response_text(chunk)
        if text:
            yield text
    if on_usage:
        on_usage(usage)
