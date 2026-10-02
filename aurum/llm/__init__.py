"""aurum.llm -- the pluggable LLM provider layer.

Adapted from the provider layer shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor):

- ``ai_providers``: one interface, five providers (OpenAI / Claude / Ollama / LM
  Studio / Custom) behind ``AIProviderFactory``.
- ``config``: provider configuration, reading provider/model from
  ``aurum.core.config.settings()`` and everything else (timeout, temperature,
  max_tokens, cache TTL) from ``AURUM_LLM_*`` environment variables.
- ``structured``: ``generate_text`` / ``generate_structured`` -- robust JSON
  extraction, Pydantic validation with retries, and an on-disk cache.
- ``router``: a FastAPI ``APIRouter`` exposing ``/llm/*``.
- ``exceptions``: ``CloudNotAllowed``, raised by the privacy gate that keeps every
  call on a local provider unless the operator opts in.

``role`` is a plain audit-only string label (default ``"research"``); it does not
affect provider selection.

See docs/modules/llm.md for the full reference.
"""

from __future__ import annotations

from .config import ProviderConfig, get_provider_config, is_local_provider
from .exceptions import CloudNotAllowed
from .structured import GenerationMeta, generate_structured, generate_text

__all__ = [
    "ProviderConfig",
    "get_provider_config",
    "is_local_provider",
    "CloudNotAllowed",
    "GenerationMeta",
    "generate_structured",
    "generate_text",
]
