"""Chat model access, over an OpenAI-compatible HTTP endpoint.

See docs/PLAN.md §4 "Local models" — chat goes over HTTP (unlike embeddings,
which load in-process) so the same code runs against mlx_lm.server, Ollama or
LM Studio by changing `STB_LLM_BASE_URL`.
"""

from smalltobig.llm.client import ChatMessage, LlmClient
from smalltobig.llm.openai_compat import OpenAICompatClient

__all__ = ["ChatMessage", "LlmClient", "OpenAICompatClient"]
