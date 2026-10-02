"""Structured (schema-validated) and plain-text generation over any AI provider.

Call the provider, pull JSON out of whatever prose/fencing it wrapped the answer in,
validate against a Pydantic model, and retry with the validation error appended to
the prompt on failure (adapted from the structured-generation helper shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor)).

- ``role`` is a plain string label threaded through for audit purposes only.
- Privacy gate: EVERY call that resolves to a cloud provider is refused
  (``CloudNotAllowed``) unless the operator has set ``AURUM_CLOUD_OPT_IN=1``;
  ``contains_raw_documents`` is an audit-only flag (it is logged, it does not change the
  decision). See :mod:`aurum.llm.exceptions` and :func:`aurum.llm.config.is_local_provider`.

Nothing here does network I/O at import time.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .ai_providers import AIProvider, AIProviderFactory
from .config import ProviderConfig, cache_dir, cache_ttl_seconds, get_provider_config, is_local_provider
from .exceptions import CloudNotAllowed

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class GenerationMeta:
    """Provenance for one generation call. Diagnostic metadata, not a durable record."""

    provider: str
    model: str
    prompt_hash: str
    latency_ms: int
    cached: bool


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA.sub(r"\1", text)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a model response.

    Handles markdown fences, leading/trailing prose (falls back to the outermost
    balanced ``{...}``/``[...]`` span), and trailing commas the model sometimes
    leaves before a closing bracket.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    candidates = [text]
    spans: list[tuple[int, str]] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            spans.append((start, text[start : end + 1]))
    candidates.extend(span for _, span in sorted(spans, key=lambda c: c[0]))

    last_error: Exception | None = None
    for candidate in candidates:
        for variant in (candidate, _strip_trailing_commas(candidate)):
            try:
                return json.loads(variant)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue

    raise ValueError(f"could not parse JSON from model response: {last_error}")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_key(provider: str, model: str, prompt: str, schema_name: str) -> str:
    digest = hashlib.sha256()
    digest.update(provider.encode("utf-8"))
    digest.update(b"\0")
    digest.update(model.encode("utf-8"))
    digest.update(b"\0")
    digest.update(prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(schema_name.encode("utf-8"))
    return digest.hexdigest()


def _cache_path(key: str) -> Path:
    return Path(cache_dir()) / f"{key}.json"


def _cache_read(key: str) -> dict[str, Any] | None:
    ttl = cache_ttl_seconds()
    if ttl <= 0:
        return None
    path = _cache_path(key)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_write(key: str, payload: dict[str, Any]) -> None:
    if cache_ttl_seconds() <= 0:
        return
    path = _cache_path(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.warning("Failed to write LLM cache entry %s", key, exc_info=True)


# ---------------------------------------------------------------------------
# Provider plumbing
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async provider call from synchronous callers (CLI, tests)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        raise RuntimeError(
            "generate_text/generate_structured are synchronous; call from a sync "
            "context or use the provider directly inside an async route"
        )


def build_provider(cfg: ProviderConfig):
    return AIProviderFactory.create_provider(
        AIProvider(cfg.provider), cfg.api_key, cfg.model, cfg.base_url
    )


def _resolve_config(provider_cfg: ProviderConfig | None, role: str) -> ProviderConfig:
    if provider_cfg is not None:
        return provider_cfg
    return get_provider_config(role)


def _check_privacy_gate(cfg: ProviderConfig, contains_raw_documents: bool) -> None:
    """Refuse to route ANY call to a cloud provider unless the operator opted in.

    Local providers (ollama, lm_studio, or custom pointed at localhost) are always
    allowed. Anthropic/OpenAI (and a non-local custom base_url) are refused unless
    ``AURUM_CLOUD_OPT_IN=1`` — the prompt's content (a ledger digest, a payee list, a
    research question) is the user's financial data whether or not it embeds a raw
    document, so ``contains_raw_documents`` only annotates the audit log now.
    """
    if is_local_provider(cfg):
        return
    from aurum.core.config import settings

    if settings().cloud_opt_in:
        if contains_raw_documents:
            logger.info("cloud provider %s receiving raw documents (AURUM_CLOUD_OPT_IN=1)", cfg.provider)
        return
    raise CloudNotAllowed(
        f"refusing to call cloud provider '{cfg.provider}' (model '{cfg.model}'"
        f"{', raw documents' if contains_raw_documents else ''}); use a local provider "
        "(ollama, lm_studio, or a custom endpoint on localhost) or set AURUM_CLOUD_OPT_IN=1"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_text(
    prompt: str,
    provider_cfg: ProviderConfig | None = None,
    *,
    role: str = "research",
    system_prompt: str | None = None,
    cache: bool = True,
    contains_raw_documents: bool = False,
) -> tuple[str, GenerationMeta]:
    """Generate plain text via the configured provider.

    Returns ``(text, meta)``. ``role`` is an audit-only label. Set
    ``contains_raw_documents=True`` when the prompt embeds raw source-document
    content; this enforces the local-provider privacy gate (see module docstring).
    """
    cfg = _resolve_config(provider_cfg, role)
    _check_privacy_gate(cfg, contains_raw_documents)

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    key = _cache_key(cfg.provider, cfg.model, prompt, "__text__")

    if cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached["text"], GenerationMeta(
                provider=cfg.provider,
                model=cfg.model,
                prompt_hash=prompt_hash,
                latency_ms=0,
                cached=True,
            )

    provider = build_provider(cfg)
    start = time.monotonic()
    text = _run_async(
        provider.generate_text(
            prompt,
            system_prompt=system_prompt,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    if cache:
        _cache_write(key, {"text": text})

    return text, GenerationMeta(
        provider=cfg.provider,
        model=cfg.model,
        prompt_hash=prompt_hash,
        latency_ms=latency_ms,
        cached=False,
    )


def _reject_schema_echo(parsed: Any, schema: type[BaseModel]) -> None:
    """Fail loudly when the model returns the JSON *schema* instead of an instance."""
    if not isinstance(parsed, dict):
        return
    keywords = {"$defs", "$schema", "properties", "definitions"}
    fields = set(schema.model_fields)
    if keywords & set(parsed) and not (fields & set(parsed)):
        raise ValueError(
            "the reply is the JSON schema itself, not an object matching it; "
            "return an instance with the fields " + ", ".join(sorted(fields))
        )


def generate_structured(
    prompt: str,
    schema: type[SchemaT],
    provider_cfg: ProviderConfig | None = None,
    *,
    role: str = "research",
    retries: int = 2,
    cache: bool = True,
    system_prompt: str | None = None,
    contains_raw_documents: bool = False,
) -> tuple[SchemaT, GenerationMeta]:
    """Generate JSON matching ``schema`` via the configured provider.

    Retries up to ``retries`` additional times, appending the validation error to the
    prompt each time, before raising. Results are cached on disk keyed on
    ``sha256(provider + model + prompt + schema.__name__)`` (see :mod:`.config` for
    the TTL env var). ``role`` is an audit-only label. Set
    ``contains_raw_documents=True`` to enforce the local-provider privacy gate.
    """
    cfg = _resolve_config(provider_cfg, role)
    _check_privacy_gate(cfg, contains_raw_documents)

    schema_name = schema.__name__
    prompt_hash = hashlib.sha256(f"{prompt}\0{schema_name}".encode()).hexdigest()
    key = _cache_key(cfg.provider, cfg.model, prompt, schema_name)

    if cache:
        cached = _cache_read(key)
        if cached is not None:
            try:
                result = schema.model_validate(cached["result"])
            except ValidationError:
                pass
            else:
                return result, GenerationMeta(
                    provider=cfg.provider,
                    model=cfg.model,
                    prompt_hash=prompt_hash,
                    latency_ms=0,
                    cached=True,
                )

    provider = build_provider(cfg)
    current_prompt = prompt
    last_error: Exception | None = None
    attempts = retries + 1
    start = time.monotonic()

    for attempt in range(attempts):
        raw = _run_async(
            provider.generate_text(
                current_prompt,
                system_prompt=system_prompt,
                json_mode=True,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
        )
        try:
            parsed = extract_json(raw)
            _reject_schema_echo(parsed, schema)
            result = schema.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "Structured parse failed (attempt %s/%s) for %s: %s",
                attempt + 1,
                attempts,
                schema_name,
                exc,
            )
            current_prompt = (
                f"{prompt}\n\nYour previous reply could not be parsed or failed "
                f"validation ({exc}). Respond again with ONLY valid JSON matching "
                "the schema, no prose, no markdown fences."
            )
            continue
        else:
            latency_ms = int((time.monotonic() - start) * 1000)
            if cache:
                _cache_write(key, {"result": result.model_dump(mode="json")})
            return result, GenerationMeta(
                provider=cfg.provider,
                model=cfg.model,
                prompt_hash=prompt_hash,
                latency_ms=latency_ms,
                cached=False,
            )

    raise ValueError(f"Model did not return valid data for {schema_name}: {last_error}")
