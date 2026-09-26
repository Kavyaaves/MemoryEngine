"""Diversity: Maximal Marginal Relevance (MMR), the optional last reranking step.

Chats repeat themselves: the same forwarded message, "ok da" five times, a photo shared in two
groups. Pure relevance ranking can fill the top results with near-copies of one memory. MMR
picks results one at a time, each time taking the memory that is

    λ · relevance  −  (1 − λ) · (similarity to the most similar memory already picked)

so a near-copy of something already picked loses to a slightly less relevant, different memory.
λ = 1.0 is pure relevance (MMR off); the MMR_LAMBDA setting controls it. Similarity is the
cosine similarity of the memories' stored embeddings (no extra AI call).
"""

import uuid

import numpy as np

MMR_POOL = 30  # only the best 30 are re-ordered; anything below keeps its place


def _relevance_0_to_1(scores: list[float]) -> list[float]:
    """Min–max scale the scores, so relevance and similarity use the same 0..1 range."""
    low, high = min(scores), max(scores)
    if high == low:
        return [1.0] * len(scores)
    return [(s - low) / (high - low) for s in scores]


def mmr_order(ranked: list[tuple[uuid.UUID, float]], vectors: dict[uuid.UUID, np.ndarray],
              lambda_: float) -> list[uuid.UUID]:
    """`ranked` is (memory id, relevance score), best first. Returns the ids in MMR order.

    Memories without a vector count as dissimilar to everything (they are never pushed down).
    """
    if lambda_ >= 1.0 or len(ranked) < 3:
        return [memory_id for memory_id, _ in ranked]

    pool, rest = ranked[:MMR_POOL], ranked[MMR_POOL:]
    ids = [memory_id for memory_id, _ in pool]
    relevance = _relevance_0_to_1([score for _, score in pool])

    # Unit-length vectors, so a dot product is the cosine similarity.
    unit: dict[uuid.UUID, np.ndarray] = {}
    for memory_id in ids:
        vector = vectors.get(memory_id)
        if vector is not None and np.linalg.norm(vector) > 0:
            unit[memory_id] = np.asarray(vector, dtype=np.float32) / np.linalg.norm(vector)

    picked: list[int] = []
    remaining = list(range(len(ids)))
    while remaining:
        def mmr_value(i: int) -> float:
            vector = unit.get(ids[i])
            if vector is None or not picked:
                redundancy = 0.0
            else:
                redundancy = max((float(vector @ unit[ids[j]]) for j in picked if ids[j] in unit), default=0.0)
            return lambda_ * relevance[i] - (1 - lambda_) * redundancy

        best = max(remaining, key=mmr_value)  # ties keep the relevance order (max returns the first)
        picked.append(best)
        remaining.remove(best)
    return [ids[i] for i in picked] + [memory_id for memory_id, _ in rest]
