"""Prompts: the answer prompt must stay long enough, and fixed, for OpenAI's prompt cache."""

import tiktoken

from app.ai.prompts import ANALYZE_SYSTEM, ANSWER_SYSTEM, RERANK_SYSTEM, VERIFY_SYSTEM

# OpenAI only caches prompts whose identical start is at least this many tokens long.
OPENAI_MIN_CACHEABLE_TOKENS = 1024


def test_answer_system_prompt_alone_is_long_enough_to_be_cached():
    tokens = tiktoken.get_encoding("o200k_base").encode(ANSWER_SYSTEM)  # the gpt-4.1 tokenizer
    assert len(tokens) >= OPENAI_MIN_CACHEABLE_TOKENS + 64  # a margin, so a small edit doesn't drop below


def test_system_prompts_are_fixed_text():
    # Anything that changes per request (dates, questions) must go into the user message,
    # or the prompt's start would differ every time and never hit the cache.
    for prompt in (ANSWER_SYSTEM, ANALYZE_SYSTEM, RERANK_SYSTEM, VERIFY_SYSTEM):
        assert "{" not in prompt and "}" not in prompt
