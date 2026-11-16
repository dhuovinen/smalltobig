"""Embeddings, in-process via mlx-embeddings.

Unlike chat (llm/), this does not go over HTTP: mlx-embeddings ships no
server, so the model loads inside the caller's process. See
docs/DECISIONS.md #10 for the tradeoff. Importing smalltobig.embed.mlx_backend
requires the optional `mlx` extra (Apple Silicon only) — keep that import
behind the call site, not at module scope, so the rest of the app stays
importable on CI.
"""
