"""mlx-embeddings backend: model load and text embedding, in-process.

Requires the optional `mlx` extra (Apple Silicon only). Import this module
lazily at the call site, never at package scope — see embed/__init__.py.
"""

from __future__ import annotations

from typing import cast

import mlx.core as mx
from mlx_embeddings import generate, load


class EmbeddingModel:
    def __init__(self, repo_id: str) -> None:
        self._model, self._processor = load(repo_id)

    def embed(self, texts: list[str]) -> mx.array:
        """Return one mean-pooled, L2-normalized embedding per input text."""
        output = generate(self._model, self._processor, texts=texts)
        embeddings = output.text_embeds
        if embeddings is None:
            raise RuntimeError("model produced no text_embeds")
        return cast("mx.array", embeddings)


def cosine_similarity(a: mx.array, b: mx.array) -> float:
    a_unit = a / mx.maximum(mx.linalg.norm(a), 1e-9)
    b_unit = b / mx.maximum(mx.linalg.norm(b), 1e-9)
    return float(mx.sum(a_unit * b_unit))
