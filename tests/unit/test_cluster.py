from __future__ import annotations

from smalltobig.embed.cluster import cluster_by_similarity, cosine_similarity


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_of_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_handles_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_empty_input_produces_no_clusters() -> None:
    assert cluster_by_similarity([]) == []


def test_single_point_is_its_own_cluster() -> None:
    clusters = cluster_by_similarity([[1.0, 0.0]])
    assert len(clusters) == 1
    assert clusters[0].indices == (0,)


def test_near_identical_points_merge_into_one_cluster() -> None:
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.99, 0.01, 0.0],
        [0.0, 1.0, 0.0],
    ]
    clusters = cluster_by_similarity(embeddings, threshold=0.9)
    assert len(clusters) == 2
    sizes = sorted(len(c.indices) for c in clusters)
    assert sizes == [1, 2]
    merged = next(c for c in clusters if len(c.indices) == 2)
    assert merged.indices == (0, 1)


def test_dissimilar_points_stay_separate() -> None:
    embeddings = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    clusters = cluster_by_similarity(embeddings, threshold=0.75)
    assert len(clusters) == 3


def test_every_index_appears_in_exactly_one_cluster() -> None:
    embeddings = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [-1.0, 0.0]]
    clusters = cluster_by_similarity(embeddings, threshold=0.8)
    seen = sorted(i for cluster in clusters for i in cluster.indices)
    assert seen == list(range(len(embeddings)))


def test_high_threshold_keeps_everything_separate() -> None:
    # Similarities here are 0.8, 0.6 and 0.0 — comfortably below 0.95.
    embeddings = [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]]
    clusters = cluster_by_similarity(embeddings, threshold=0.95)
    assert len(clusters) == 3


def test_low_threshold_merges_everything() -> None:
    embeddings = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    clusters = cluster_by_similarity(embeddings, threshold=-1.0)
    assert len(clusters) == 1
    assert clusters[0].indices == (0, 1, 2)
