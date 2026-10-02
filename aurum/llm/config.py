"""LLM provider configuration for aurum.llm.

``role`` is a plain string label threaded through calls for audit purposes only —
it enforces nothing.

Provider and model come from :func:`aurum.core.config.settings` (``AURUM_LLM_PROVIDER``
/ ``AURUM_LLM_MODEL``, already wired there) so this module has one source of truth for
those two values. Everything else — timeout, temperature, max_tokens, cache TTL — is
not in ``aurum.core.config`` and is read directly from the environment here.

Env vars
--------
``AURUM_LLM_PROVIDER``    default provider (via aurum.core.config.settings(), default ``ollama``)
``AURUM_LLM_MODEL``       default model (via aurum.core.config.settings(), default ``llama3.1:8b``;
                          with the ``claude`` provider that default becomes ``claude-opus-5-5``)
``OLLAMA_URL``            base URL for the ``ollama`` provider (default ``http://localhost:11434``)
``ANTHROPIC_API_KEY``     API key for the ``claude`` provider
``OPENAI_API_KEY``        API key for the ``openai`` provider
``AURUM_LLM_TIMEOUT_S``   seconds to wait on one provider HTTP call (default 60)
``AURUM_LLM_TEMPERATURE`` generation temperature (default 0.2)
``AURUM_LLM_MAX_TOKENS``  generation max tokens (default 2048)
``AURUM_LLM_CACHE_TTL_S`` TTL in seconds for the on-disk structured-generation cache (default 300)
``AURUM_CLOUD_OPT_IN``    (read via aurum.core.config.settings()) allows calls to cloud
                          providers at all; see :mod:`aurum.llm.exceptions`
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from aurum.core.config import settings

_TRUE = {"1", "true", "yes", "on"}

# Providers that need no API key by default (local servers).
_NO_KEY_PROVIDERS = {"ollama", "lm_studio"}

_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}

#: Providers considered inherently local, regardless of base_url.
_LOCAL_PROVIDERS = {"ollama", "lm_studio"}

#: Providers always considered cloud (never local, no matter the base_url).
_CLOUD_PROVIDERS = {"openai", "claude"}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

#: ``AURUM_LLM_MODEL``'s default (a local Ollama model).
LOCAL_DEFAULT_MODEL = "llama3.1:8b"

#: Model used with ``AURUM_LLM_PROVIDER=claude`` when ``AURUM_LLM_MODEL`` is unset or still the
#: local default.
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"


def _env_opt(name: str) -> str | None:
    value = os.environ.get(name)
    return None if value is None or value == "" else value


def _env_float(name: str, default: float) -> float:
    raw = _env_opt(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = _env_opt(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class ProviderConfig:
    """Everything :class:`~aurum.llm.ai_providers.AIProviderFactory` needs to build a
    provider, plus generation defaults."""

    provider: str
    model: str
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2048
    role: str = "research"


def _default_base_url(provider: str) -> str | None:
    if provider == "ollama":
        return settings().ollama_url
    return None


def _default_api_key(provider: str) -> str:
    if provider in _NO_KEY_PROVIDERS:
        return ""
    if provider == "claude":
        return settings().anthropic_api_key
    env_name = _API_KEY_ENV.get(provider)
    if env_name is None:
        return ""
    return os.environ.get(env_name, "")


def request_timeout() -> float:
    """Seconds to wait on one provider HTTP call (``AURUM_LLM_TIMEOUT_S``, default 60)."""
    return _env_float("AURUM_LLM_TIMEOUT_S", 60.0)


def default_temperature() -> float:
    return _env_float("AURUM_LLM_TEMPERATURE", 0.2)


def default_max_tokens() -> int:
    return _env_int("AURUM_LLM_MAX_TOKENS", 2048)


def cache_ttl_seconds() -> int:
    """TTL for the on-disk structured-generation cache. 0 disables caching."""
    return _env_int("AURUM_LLM_CACHE_TTL_S", 300)


def cache_dir() -> str:
    """``<AURUM_DATA_DIR>/cache/llm``, resolved from :func:`aurum.core.config.settings`."""
    return str(settings().data_dir / "cache" / "llm")


def get_provider_config(
    role: str = "research",
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ProviderConfig:
    """Resolve a :class:`ProviderConfig`.

    Reads provider/model from :func:`aurum.core.config.settings` unless overridden by
    the keyword args (useful for callers that want a one-off provider without setting
    env vars, and for tests). ``role`` is a free-text audit label only — it has no
    effect on which provider is used.
    """
    s = settings()
    resolved_provider = provider or s.llm_provider
    resolved_model = model or s.llm_model
    if resolved_provider == "claude" and not model and resolved_model in ("", LOCAL_DEFAULT_MODEL):
        # The global default names a local model; a Claude call needs a Claude model.
        resolved_model = DEFAULT_CLAUDE_MODEL
    resolved_base_url = base_url or _default_base_url(resolved_provider)
    resolved_api_key = api_key if api_key is not None else _default_api_key(resolved_provider)
    return ProviderConfig(
        provider=resolved_provider,
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=default_temperature(),
        max_tokens=default_max_tokens(),
        role=role,
    )


def _is_localhost(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        host = urlparse(base_url).hostname
    except ValueError:
        return False
    return host is not None and host.lower() in _LOCAL_HOSTS


def is_local_provider(cfg: ProviderConfig) -> bool:
    """True if ``cfg`` routes to a provider that keeps data on this machine.

    Ollama and LM Studio are always local. Custom is local only if its base_url
    points at localhost/127.0.0.1. OpenAI and Claude are always cloud.
    """
    if cfg.provider in _CLOUD_PROVIDERS:
        return False
    if cfg.provider in _LOCAL_PROVIDERS:
        return True
    if cfg.provider == "custom":
        return _is_localhost(cfg.base_url)
    # Unknown provider: treat as not-local (fail closed for the privacy gate).
    return False
