"""Agglomerative clustering of claim embeddings by cosine similarity.

Hand-rolled average-linkage rather than a scikit-learn dependency: claim
counts here are small (dozens to low hundreds per synthesis run, per
docs/DECISIONS.md #11 — "a batch job run rarely on a handful of sources"),
and this is the only place clustering is needed. Pure Python — no mlx
import — so it's testable without the `mlx` extra; only the embeddings
themselves come from embed/mlx_backend.py.

The right threshold is embedding-model-dependent and meant to be "tuned
by hand on the seed set" (docs/PLAN.md §2 Stage 3) — `stb synthesize
--threshold` exposes it. The default below is calibrated for
mlx-community/all-MiniLM-L6-v2-bf16 (the doctor/config default): live
testing on real claim paraphrases from that model put same-topic pairs
around 0.5-0.56 cosine similarity, well under a naive 0.75 guess — see
docs/DECISIONS.md #11's amendment.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SIMILARITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class Cluster:
    indices: tuple[int, ...]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def cluster_by_similarity(
    embeddings: list[list[float]], *, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> list[Cluster]:
    """Average-linkage (UPGMA): repeatedly merge whichever pair of clusters
    has the highest average pairwise similarity, stopping once the best
    remaining merge falls below `threshold`."""
    n = len(embeddings)
    if n == 0:
        return []
    if n == 1:
        return [Cluster(indices=(0,))]

    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    sim: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim[(i, j)] = cosine_similarity(embeddings[i], embeddings[j])

    def get_sim(a: int, b: int) -> float:
        return sim[(a, b)] if a < b else sim[(b, a)]

    def set_sim(a: int, b: int, value: float) -> None:
        key = (a, b) if a < b else (b, a)
        sim[key] = value

    active = set(members.keys())
    next_id = n

    while len(active) > 1:
        active_list = sorted(active)
        best_pair: tuple[int, int] | None = None
        best_score = threshold
        for x in range(len(active_list)):
            for y in range(x + 1, len(active_list)):
                a, b = active_list[x], active_list[y]
                score = get_sim(a, b)
                if score > best_score:
                    best_score = score
                    best_pair = (a, b)
        if best_pair is None:
            break

        a, b = best_pair
        size_a, size_b = len(members[a]), len(members[b])
        merged_id = next_id
        next_id += 1
        members[merged_id] = members[a] + members[b]

        # Lance-Williams update for average linkage: the new cluster's
        # similarity to every other active cluster is the size-weighted
        # average of its two parents' similarities to that cluster.
        for other in active - {a, b}:
            merged_sim = (size_a * get_sim(a, other) + size_b * get_sim(b, other)) / (
                size_a + size_b
            )
            set_sim(merged_id, other, merged_sim)

        active -= {a, b}
        active.add(merged_id)

    return [Cluster(indices=tuple(sorted(members[c]))) for c in sorted(active)]
