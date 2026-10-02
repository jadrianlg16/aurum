"""Offline tests for aurum.llm: JSON extraction, provider dispatch, privacy gate,
and env var defaults. No real network calls -- httpx clients are monkeypatched."""

from __future__ import annotations

import json

import pytest

from aurum.llm import config as llm_config
from aurum.llm.ai_providers import AIProvider, AIProviderFactory
from aurum.llm.config import ProviderConfig, get_provider_config, is_local_provider
from aurum.llm.exceptions import CloudNotAllowed
from aurum.llm.structured import extract_json, generate_structured, generate_text

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def test_extract_json_raw():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = 'Sure, here you go:\n```json\n{"a": 1, "b": 2}\n```\nThanks!'
    assert extract_json(text) == {"a": 1, "b": 2}


def test_extract_json_fenced_no_language():
    text = '```\n{"x": true}\n```'
    assert extract_json(text) == {"x": True}


def test_extract_json_balanced_brace_fallback():
    text = 'The answer is {"a": 1, "nested": {"b": 2}} -- hope that helps.'
    assert extract_json(text) == {"a": 1, "nested": {"b": 2}}


def test_extract_json_array_fallback():
    text = "Here: [1, 2, 3] done."
    assert extract_json(text) == [1, 2, 3]


def test_extract_json_trailing_comma():
    text = '{"a": 1, "b": 2,}'
    assert extract_json(text) == {"a": 1, "b": 2}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


def test_extract_json_unparseable_raises():
    with pytest.raises(ValueError):
        extract_json("not json at all, no braces")


# ---------------------------------------------------------------------------
# Provider dispatch (factory only -- no network)
# ---------------------------------------------------------------------------


def test_factory_builds_each_provider():
    for provider in AIProvider:
        if provider == AIProvider.CUSTOM:
            instance = AIProviderFactory.create_provider(
                provider, "key", "model", "http://localhost:9999/v1"
            )
        else:
            instance = AIProviderFactory.create_provider(provider, "key", "model")
        assert instance.model_name == "model"


def test_factory_custom_requires_base_url():
    with pytest.raises(ValueError):
        AIProviderFactory.create_provider(AIProvider.CUSTOM, "key", "model", None)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        AIProviderFactory.create_provider("not-a-provider", "key", "model")  # type: ignore[arg-type]


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Drop-in replacement for httpx.AsyncClient used as an async context manager."""

    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        _FakeAsyncClient.calls.append((url, kwargs))
        if "/api/generate" in url:
            return _FakeResponse({"response": "ollama says hi"})
        if "anthropic" in url or "/messages" in url:
            return _FakeResponse({"content": [{"type": "text", "text": "claude says hi"}], "stop_reason": "end_turn"})
        return _FakeResponse({"choices": [{"message": {"content": "openai-shaped says hi"}}]})


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every test in this module runs with httpx fully mocked out."""
    import httpx

    _FakeAsyncClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    yield


def test_generate_text_ollama_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AURUM_LLM_MODEL", "llama3.1:8b")
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    text, meta = generate_text("hello", cache=False)
    assert text == "ollama says hi"
    assert meta.provider == "ollama"
    assert meta.model == "llama3.1:8b"
    assert meta.cached is False


def test_generate_text_claude_dispatch(monkeypatch, tmp_path):
    # a cloud provider needs the opt-in for every call.
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    cfg = ProviderConfig(provider="claude", model="claude-opus-5-5", api_key="sk-test")
    text, meta = generate_text("hello", provider_cfg=cfg, cache=False)
    assert text == "claude says hi"
    assert meta.provider == "claude"


def test_generate_structured_roundtrip(monkeypatch, tmp_path):
    from pydantic import BaseModel

    class Reply(BaseModel):
        message: str

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))

    async def fake_generate_text(self, prompt, **kwargs):
        return json.dumps({"message": "hi"})

    monkeypatch.setattr(
        "aurum.llm.ai_providers.OllamaProvider.generate_text", fake_generate_text
    )
    cfg = ProviderConfig(provider="ollama", model="llama3.1:8b")
    result, meta = generate_structured("say hi", Reply, provider_cfg=cfg, cache=False)
    assert result.message == "hi"
    assert meta.provider == "ollama"


def test_generate_structured_cache_roundtrip(monkeypatch, tmp_path):
    from pydantic import BaseModel

    class Reply(BaseModel):
        message: str

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_LLM_CACHE_TTL_S", "300")

    calls = {"n": 0}

    async def fake_generate_text(self, prompt, **kwargs):
        calls["n"] += 1
        return json.dumps({"message": "hi"})

    monkeypatch.setattr(
        "aurum.llm.ai_providers.OllamaProvider.generate_text", fake_generate_text
    )
    cfg = ProviderConfig(provider="ollama", model="llama3.1:8b")
    generate_structured("say hi", Reply, provider_cfg=cfg, cache=True)
    generate_structured("say hi", Reply, provider_cfg=cfg, cache=True)
    assert calls["n"] == 1  # second call was served from cache


# ---------------------------------------------------------------------------
# Privacy gate
# ---------------------------------------------------------------------------


def test_privacy_gate_allows_local_ollama(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    cfg = ProviderConfig(provider="ollama", model="llama3.1:8b")
    text, _meta = generate_text("contains a raw statement", provider_cfg=cfg, cache=False,
                                 contains_raw_documents=True)
    assert text == "ollama says hi"


def test_privacy_gate_blocks_cloud_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AURUM_CLOUD_OPT_IN", raising=False)
    cfg = ProviderConfig(provider="claude", model="claude-opus-5-5", api_key="sk-test")
    with pytest.raises(CloudNotAllowed):
        generate_text("contains a raw statement", provider_cfg=cfg, cache=False,
                       contains_raw_documents=True)


def test_privacy_gate_allows_cloud_with_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    cfg = ProviderConfig(provider="claude", model="claude-opus-5-5", api_key="sk-test")
    text, _meta = generate_text("contains a raw statement", provider_cfg=cfg, cache=False,
                                 contains_raw_documents=True)
    assert text == "claude says hi"


def test_privacy_gate_applies_to_every_cloud_call(tmp_path, monkeypatch):
    """The gate refuses any cloud call without AURUM_CLOUD_OPT_IN, whether or not the prompt carries raw
    documents, before any HTTP is attempted."""
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AURUM_CLOUD_OPT_IN", raising=False)
    cfg = ProviderConfig(provider="claude", model="claude-opus-5-5", api_key="sk-test")
    with pytest.raises(CloudNotAllowed):
        generate_text("no raw docs here", provider_cfg=cfg, cache=False)
    assert _FakeAsyncClient.calls == []


def test_privacy_gate_env_provider_claude_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("AURUM_CLOUD_OPT_IN", raising=False)
    with pytest.raises(CloudNotAllowed):
        generate_text("x", role="insights_digest", cache=False)
    assert _FakeAsyncClient.calls == []
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    text, _meta = generate_text("x", role="insights_digest", cache=False)
    assert text == "claude says hi"
    assert len(_FakeAsyncClient.calls) == 1


def test_privacy_gate_ollama_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "ollama")
    monkeypatch.delenv("AURUM_CLOUD_OPT_IN", raising=False)
    text, _meta = generate_text("x", cache=False)
    assert text == "ollama says hi"


def test_is_local_provider():
    assert is_local_provider(ProviderConfig(provider="ollama", model="m")) is True
    assert is_local_provider(ProviderConfig(provider="lm_studio", model="m")) is True
    assert is_local_provider(ProviderConfig(provider="claude", model="m")) is False
    assert is_local_provider(ProviderConfig(provider="openai", model="m")) is False
    assert (
        is_local_provider(ProviderConfig(provider="custom", model="m", base_url="http://localhost:8080"))
        is True
    )
    assert (
        is_local_provider(ProviderConfig(provider="custom", model="m", base_url="https://example.com"))
        is False
    )
    assert is_local_provider(ProviderConfig(provider="custom", model="m", base_url=None)) is False


# ---------------------------------------------------------------------------
# Env var defaults
# ---------------------------------------------------------------------------


def test_request_timeout_default(monkeypatch):
    monkeypatch.delenv("AURUM_LLM_TIMEOUT_S", raising=False)
    assert llm_config.request_timeout() == 60.0


def test_request_timeout_override(monkeypatch):
    monkeypatch.setenv("AURUM_LLM_TIMEOUT_S", "12.5")
    assert llm_config.request_timeout() == 12.5


def test_temperature_and_max_tokens_defaults(monkeypatch):
    monkeypatch.delenv("AURUM_LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("AURUM_LLM_MAX_TOKENS", raising=False)
    assert llm_config.default_temperature() == 0.2
    assert llm_config.default_max_tokens() == 2048


def test_cache_ttl_default(monkeypatch):
    monkeypatch.delenv("AURUM_LLM_CACHE_TTL_S", raising=False)
    assert llm_config.cache_ttl_seconds() == 300


def test_get_provider_config_uses_aurum_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AURUM_LLM_MODEL", "llama3.1:8b")
    cfg = get_provider_config()
    assert cfg.provider == "ollama"
    assert cfg.model == "llama3.1:8b"
    assert cfg.role == "research"


def test_get_provider_config_default_model_is_llama31_8b(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AURUM_LLM_MODEL", raising=False)
    cfg = get_provider_config()
    assert cfg.model == "llama3.1:8b"
    assert cfg.model != "llama3.2"


# ---------------------------------------------------------------------------
# Claude Messages API handling (mocked HTTP only; no live call is made)
# ---------------------------------------------------------------------------


def _claude_cfg():
    return ProviderConfig(provider="claude", model="claude-opus-5-5", api_key="sk-test")


def _claude_reply(monkeypatch, body: dict):
    """Make the fake client answer every Claude call with ``body``."""

    async def post(self, url, **kwargs):
        _FakeAsyncClient.calls.append((url, kwargs))
        return _FakeResponse(body)

    monkeypatch.setattr(_FakeAsyncClient, "post", post)


def test_claude_payload_has_no_temperature_and_a_16k_floor(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    generate_text("hello", provider_cfg=_claude_cfg(), cache=False)
    url, kwargs = _FakeAsyncClient.calls[-1]
    assert url.endswith("/messages")
    payload = kwargs["json"]
    assert "temperature" not in payload
    assert payload["max_tokens"] >= 16000
    assert payload["model"] == "claude-opus-5-5"


def test_claude_reads_the_text_block_after_a_thinking_block(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    _claude_reply(monkeypatch, {
        "content": [
            {"type": "thinking", "thinking": "working it out", "signature": "x"},
            {"type": "text", "text": "the answer"},
        ],
        "stop_reason": "end_turn",
    })
    text, _meta = generate_text("hello", provider_cfg=_claude_cfg(), cache=False)
    assert text == "the answer"


def test_claude_refusal_raises_a_clear_provider_error(monkeypatch, tmp_path):
    from aurum.llm.exceptions import ProviderRefused

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    _claude_reply(monkeypatch, {"content": [], "stop_reason": "refusal"})
    with pytest.raises(ProviderRefused, match="refusal"):
        generate_text("hello", provider_cfg=_claude_cfg(), cache=False)


def test_claude_max_tokens_raises_a_truncation_error(monkeypatch, tmp_path):
    from aurum.llm.exceptions import ProviderTruncated

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_CLOUD_OPT_IN", "1")
    _claude_reply(monkeypatch, {"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"})
    with pytest.raises(ProviderTruncated, match="max_tokens"):
        generate_text("hello", provider_cfg=_claude_cfg(), cache=False)


def test_claude_provider_errors_are_value_errors_so_callers_can_fall_back():
    from aurum.llm.exceptions import ProviderRefused, ProviderResponseError, ProviderTruncated

    assert issubclass(ProviderRefused, ValueError)
    assert issubclass(ProviderTruncated, ProviderResponseError)


def test_claude_provider_defaults_to_opus_when_the_model_is_the_local_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "claude")
    monkeypatch.setenv("AURUM_LLM_MODEL", "llama3.1:8b")
    assert get_provider_config().model == "claude-opus-5-5"
    monkeypatch.setenv("AURUM_LLM_MODEL", "claude-custom-model")
    assert get_provider_config().model == "claude-custom-model"
