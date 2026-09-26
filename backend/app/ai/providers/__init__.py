"""AI providers and the router that picks between them.

    base.py            the interface every provider implements, TokenUsage, errors
    openai.py          the OpenAI provider (chat through LangChain, the rest through the SDK)
    langchain_utils.py message and usage adapters for LangChain chat models
    router.py          retries, quota guard, usage logging — get_router() is the entry point

Import from the modules themselves (e.g. `from app.ai.providers.router import get_router`).
This file deliberately imports nothing: re-exporting the router here made
`app.ai.usage` → `providers.base` → this file → `router` → `app.ai.usage` a circular import.
"""
