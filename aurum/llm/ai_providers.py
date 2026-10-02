"""
ai_providers.py

Provider implementations behind AIProviderInterface + AIProviderFactory: OpenAI /
Claude / Ollama / LM Studio / Custom (any OpenAI-compatible endpoint). Shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor). Timeouts read ``AURUM_LLM_TIMEOUT_S`` (via
:func:`aurum.llm.config.request_timeout`).

See docs/modules/llm.md for how aurum.llm wraps this module.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import StrEnum

import httpx

from .exceptions import ProviderRefused, ProviderResponseError, ProviderTruncated

logger = logging.getLogger(__name__)

#: Fallback when this file is used standalone and .config is not importable.
DEFAULT_TIMEOUT_S = 120.0


def request_timeout() -> float:
    """Seconds to wait on one provider HTTP call: AURUM_LLM_TIMEOUT_S, default 60.

    Read per call rather than at import, so a process can change it without a
    restart -- and so a test can monkeypatch the environment.
    """
    try:
        from .config import request_timeout as _configured

        return _configured()
    except Exception:  # pragma: no cover - defensive; keeps this file standalone
        import os

        try:
            return float(os.environ.get("AURUM_LLM_TIMEOUT_S") or DEFAULT_TIMEOUT_S)
        except ValueError:
            return DEFAULT_TIMEOUT_S


class AIProvider(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    CUSTOM = "custom"


#: Providers considered "local" (no data leaves the machine). Used by the privacy
#: gate in :mod:`aurum.llm.structured` — CUSTOM is local only if its base_url host
#: is localhost/127.0.0.1, which is checked separately.
LOCAL_PROVIDERS = {AIProvider.OLLAMA, AIProvider.LM_STUDIO}


class AIProviderInterface(ABC):
    """Abstract interface for AI providers."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        """Generate text response."""


class OpenAIProvider(AIProviderInterface):
    """OpenAI provider implementation."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self.base_url = base_url or "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"] or ""

        except Exception as e:
            logger.error(f"OpenAI provider text generation failed: {e}")
            raise


#: Output-token floor for Claude: adaptive thinking spends tokens before the visible answer.
CLAUDE_MAX_TOKENS = 16000


def claude_text(data: dict) -> str:
    """The answer text from a Messages API response body.

    Raises :class:`ProviderRefused` when the model declined (``stop_reason == "refusal"``),
    :class:`ProviderTruncated` when it ran out of output tokens, and
    :class:`ProviderResponseError` when no text block came back. Thinking blocks can come
    before the text, so the first block whose ``type`` is ``"text"`` is used.
    """
    stop_reason = data.get("stop_reason")
    if stop_reason == "refusal":
        raise ProviderRefused("Claude declined to answer this request (stop_reason=refusal)")
    if stop_reason == "max_tokens":
        raise ProviderTruncated(
            f"Claude's answer was cut off at the output-token limit (stop_reason=max_tokens, "
            f"max_tokens={CLAUDE_MAX_TOKENS} or AURUM_LLM_MAX_TOKENS if higher)"
        )
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text") or ""
    raise ProviderResponseError(f"Claude response had no text block (stop_reason={stop_reason!r})")


class ClaudeProvider(AIProviderInterface):
    """Anthropic Claude provider implementation (raw HTTP to the Messages API)."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self.base_url = base_url or "https://api.anthropic.com/v1"
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        """Call the Messages API and return the first text block.

        ``temperature`` is accepted for interface compatibility but never sent: current
        Claude models reject non-default sampling parameters. Those models also think
        adaptively and the thinking tokens count toward ``max_tokens``, so the limit is
        raised to at least :data:`CLAUDE_MAX_TOKENS`.
        """
        try:
            payload = {
                "model": self.model_name,
                "max_tokens": max(max_tokens, CLAUDE_MAX_TOKENS),
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                payload["system"] = system_prompt
            if json_mode:
                # Claude has no direct JSON mode; ask for it in the prompt.
                payload["messages"][0]["content"] += "\n\nPlease respond with valid JSON only."

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
            return claude_text(data)

        except Exception as e:
            logger.error(f"Claude provider text generation failed: {e}")
            raise


class OllamaProvider(AIProviderInterface):
    """Ollama local provider implementation."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self.base_url = base_url or "http://localhost:11434"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            if system_prompt:
                payload["system"] = system_prompt
            if json_mode:
                payload["format"] = "json"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")

        except Exception as e:
            logger.error(f"Ollama provider text generation failed: {e}")
            raise


class LMStudioProvider(AIProviderInterface):
    """LM Studio local provider implementation."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        self.base_url = base_url or "http://localhost:1234/v1"
        self.headers = {"Content-Type": "application/json"}
        if api_key and api_key != "not-needed":
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"] or ""

        except Exception as e:
            logger.error(f"LM Studio provider text generation failed: {e}")
            raise


class CustomProvider(AIProviderInterface):
    """Custom API provider implementation (OpenAI-compatible)."""

    def __init__(self, api_key: str, model_name: str, base_url: str | None = None):
        super().__init__(api_key, model_name, base_url)
        if not base_url:
            raise ValueError("Custom provider requires base_url")
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"] or ""

        except Exception as e:
            logger.error(f"Custom provider text generation failed: {e}")
            raise


class AIProviderFactory:
    """Factory for creating AI provider instances."""

    @staticmethod
    def create_provider(
        provider: AIProvider, api_key: str, model_name: str, base_url: str | None = None
    ) -> AIProviderInterface:
        if provider == AIProvider.OPENAI:
            return OpenAIProvider(api_key, model_name, base_url)
        elif provider == AIProvider.CLAUDE:
            return ClaudeProvider(api_key, model_name, base_url)
        elif provider == AIProvider.OLLAMA:
            return OllamaProvider(api_key, model_name, base_url)
        elif provider == AIProvider.LM_STUDIO:
            return LMStudioProvider(api_key, model_name, base_url)
        elif provider == AIProvider.CUSTOM:
            return CustomProvider(api_key, model_name, base_url)
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")

    @staticmethod
    def get_available_providers() -> list[str]:
        return [provider.value for provider in AIProvider]
