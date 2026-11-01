"""Merging the results of several search paths with Reciprocal Rank Fusion (RRF).

Each path ranks memories by its own kind of score, and those scores aren't comparable
(a trigram similarity of 0.6 vs a cosine similarity of 0.6 mean different things). RRF
only uses each memory's *position* in each list:

    score(memory) = Σ over paths   weight(path) / (k + rank in that path)

so a memory ranked highly by several paths beats one ranked first by only one path.
"""

import uuid
from dataclasses import dataclass, field

from app.retrieval.query import Candidate

# "book" (Graph RAG, retrieval/books.py) is also semantic, so it weighs a little less than
# "vector": a memory both find still gets the agreement bonus without meaning counting twice.
PATH_WEIGHTS = {"fts": 1.0, "trgm": 0.6, "vector": 1.0, "graph": 0.8, "temporal": 1.2, "book": 0.8}


@dataclass
class FusedCandidate:
    memory_id: uuid.UUID
    score: float
    paths: list[str] = field(default_factory=list)  # which search paths found it
    path_scores: dict[str, float] = field(default_factory=dict)  # each path's own score


def rrf_fuse(results_by_path: dict[str, list[Candidate]], k: int = 60,
             weights: dict[str, float] | None = None) -> list[FusedCandidate]:
    weights = weights or PATH_WEIGHTS
    fused: dict[uuid.UUID, FusedCandidate] = {}
    for path, candidates in results_by_path.items():
        weight = weights.get(path, 1.0)
        rank = 0
        seen: set[uuid.UUID] = set()
        for candidate in candidates:
            if candidate.memory_id in seen:
                continue  # a path may return the same memory twice (e.g. two query variants)
            seen.add(candidate.memory_id)
            rank += 1
            entry = fused.setdefault(candidate.memory_id, FusedCandidate(candidate.memory_id, 0.0))
            entry.score += weight / (k + rank)
            entry.paths.append(path)
            entry.path_scores[path] = candidate.score
    return sorted(fused.values(), key=lambda entry: entry.score, reverse=True)
