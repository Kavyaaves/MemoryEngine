"""Hosted AI only — no local models (PLAN §2).

    providers/   OpenAI behind one interface, plus the router that retries, guards quotas and logs usage
    usage.py     quota guard + usage log
    embeddings.py text → vectors for semantic search
    prompts/     every prompt the app sends, versioned
"""
