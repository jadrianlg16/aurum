"""FX endpoints, mounted at ``/api/fx``."""

from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import store
from .rates import FxRateNotFound, cache_rate, get_rate

router = APIRouter(tags=["fx"])


class RateBody(BaseModel):
    base: str
    quote: str
    date: date_cls
    rate: Decimal


@router.get("/rate")
def api_get_rate(base: str, quote: str, date: date_cls | None = None) -> dict:
    on = date or date_cls.today()
    try:
        rate = get_rate(base, quote, on)
    except FxRateNotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"base": base.upper(), "quote": quote.upper(), "date": on.isoformat(), "rate": str(rate)}


@router.post("/rate")
def api_set_rate(body: RateBody) -> dict:
    cache_rate(body.base.upper(), body.quote.upper(), body.date, body.rate, source="manual")
    return {"ok": True}


@router.get("/rates")
def api_list_rates(base: str | None = None, quote: str | None = None) -> list[dict]:
    conn = store.db()
    q = "SELECT base, quote, date, rate, source FROM fx_rates WHERE 1=1"
    args: list[str] = []
    if base:
        q += " AND base=?"
        args.append(base.upper())
    if quote:
        q += " AND quote=?"
        args.append(quote.upper())
    q += " ORDER BY date DESC LIMIT 200"
    rows = conn.execute(q, args).fetchall()
    return [dict(r) for r in rows]
