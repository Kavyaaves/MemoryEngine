"""Retrieval metrics (PLAN §36): Hit rate@K, Recall@K, MRR, NDCG@K, plus latency percentiles.

    hit_rate@k  1 if any relevant memory is in the top k, else 0 — averaged, this is the share of
                questions the search "gets right" (the headline "retrieval accuracy")
    recall@k    share of *all* relevant memories found in the top k
    mrr         1 / rank of the first relevant memory (1.0 = it came first)
    ndcg@k      like recall, but rewards putting relevant memories higher; supports graded relevance
"""

import math
from collections.abc import Mapping, Sequence


def hit_rate_at_k(retrieved: Sequence[str], relevant: set[str] | Mapping[str, float], k: int) -> float:
    return 1.0 if set(relevant) & set(retrieved[:k]) else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: set[str] | Mapping[str, float], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    return len(rel & set(retrieved[:k])) / len(rel)


def mrr(retrieved: Sequence[str], relevant: set[str] | Mapping[str, float]) -> float:
    rel = set(relevant)
    for i, r in enumerate(retrieved, 1):
        if r in rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: set[str] | Mapping[str, float], k: int) -> float:
    gains = relevant if isinstance(relevant, Mapping) else {r: 1.0 for r in relevant}
    if not gains:
        return 0.0
    dcg = sum(gains.get(r, 0.0) / math.log2(i + 1) for i, r in enumerate(retrieved[:k], 1))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0


def percentile(values: Sequence[float], p: float) -> float:
    """The p-th percentile (0–100) with linear interpolation, e.g. percentile(latencies, 50) = median."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    """Average every metric over the rows; latency also gets its median (p50) and p95."""
    if not rows:
        return {}
    keys = rows[0].keys()
    summary = {k: round(sum(r[k] for r in rows) / len(rows), 4) for k in keys}
    if "latency_ms" in keys:
        latencies = [r["latency_ms"] for r in rows]
        summary["latency_p50_ms"] = round(percentile(latencies, 50), 1)
        summary["latency_p95_ms"] = round(percentile(latencies, 95), 1)
    summary["n"] = len(rows)
    return summary
