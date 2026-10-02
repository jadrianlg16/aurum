"""FastAPI router exposing aurum.llm over HTTP.

``role`` is a plain audit-only label; a ``CloudNotAllowed`` from the privacy gate is
turned into an HTTP error. This module must import cleanly with no network access --
provider calls only happen inside request handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, create_model

from .config import get_provider_config
from .exceptions import CloudNotAllowed
from .structured import GenerationMeta, generate_structured, generate_text

router = APIRouter(prefix="/llm", tags=["llm"])


class GenerateRequest(BaseModel):
    prompt: str
    role: str = "research"
    system_prompt: str | None = None
    cache: bool = True
    contains_raw_documents: bool = False


class GenerationMetaOut(BaseModel):
    provider: str
    model: str
    prompt_hash: str
    latency_ms: int
    cached: bool

    @classmethod
    def from_meta(cls, meta: GenerationMeta) -> GenerationMetaOut:
        return cls(
            provider=meta.provider,
            model=meta.model,
            prompt_hash=meta.prompt_hash,
            latency_ms=meta.latency_ms,
            cached=meta.cached,
        )


class GenerateResponse(BaseModel):
    text: str
    meta: GenerationMetaOut


class StructuredRequest(BaseModel):
    prompt: str
    schema_: dict[str, Any] = Field(
        alias="schema",
        description=(
            "A flat JSON-schema-like field map, e.g. "
            '{"answer": "str", "confidence": "int"}. Only a small subset of JSON '
            "Schema is supported -- this endpoint is for simple, ad-hoc callers; "
            "code that owns a real Pydantic model should call "
            "aurum.llm.structured.generate_structured directly."
        ),
    )
    role: str = "research"
    system_prompt: str | None = None
    retries: int = 2
    cache: bool = True
    contains_raw_documents: bool = False

    model_config = {"populate_by_name": True}


class StructuredResponse(BaseModel):
    result: dict[str, Any]
    meta: GenerationMetaOut


_TYPE_MAP: dict[str, Any] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
}


def _build_dynamic_schema(fields: dict[str, Any]) -> type[BaseModel]:
    """Build a throwaway Pydantic model from a flat {field: type-name} map."""
    resolved: dict[str, Any] = {}
    for name, type_name in fields.items():
        py_type = _TYPE_MAP.get(str(type_name).lower())
        if py_type is None:
            raise HTTPException(
                status_code=400, detail=f"Unsupported field type '{type_name}' for '{name}'"
            )
        resolved[name] = (py_type, ...)
    return create_model("DynamicStructuredResponse", **resolved)  # type: ignore[call-overload]


@router.get("/health")
def health() -> dict[str, Any]:
    """Reports the configured provider without making any network calls."""
    cfg = get_provider_config()
    return {"status": "ok", "provider": cfg.provider, "model": cfg.model}


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        text, meta = generate_text(
            req.prompt,
            role=req.role,
            system_prompt=req.system_prompt,
            cache=req.cache,
            contains_raw_documents=req.contains_raw_documents,
        )
    except CloudNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the caller
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GenerateResponse(text=text, meta=GenerationMetaOut.from_meta(meta))


@router.post("/structured", response_model=StructuredResponse)
def structured(req: StructuredRequest) -> StructuredResponse:
    model_cls = _build_dynamic_schema(req.schema_)
    try:
        result, meta = generate_structured(
            req.prompt,
            model_cls,
            role=req.role,
            retries=req.retries,
            cache=req.cache,
            system_prompt=req.system_prompt,
            contains_raw_documents=req.contains_raw_documents,
        )
    except CloudNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StructuredResponse(
        result=result.model_dump(mode="json"), meta=GenerationMetaOut.from_meta(meta)
    )
