"""Credit report endpoints, mounted at ``/api/creditreport``."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core.i18n import ws_lang
from . import store
from .parser import MissingPdfEngine, parse_pdf_bytes

router = APIRouter(tags=["creditreport"])


@router.post("/{ws}/import")
async def api_import(ws: str, file: UploadFile = File(...)) -> dict:  # noqa: B008
    data = await file.read()
    try:
        report = parse_pdf_bytes(data)
    except MissingPdfEngine as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"could not read PDF: {e}") from e
    return store.save_import(ws, file.filename or "report.pdf", report)


@router.get("/{ws}")
def api_get(ws: str) -> dict:
    imports = store.list_imports(ws)
    return {"imports": imports, "latest": imports[0] if imports else None}


@router.get("/{ws}/explain")
def api_explain(ws: str, lang: str | None = None) -> dict:
    return store.explain_score_factors(lang=ws_lang(ws, lang)).model_dump(mode="json")
