"""Holdings endpoints, mounted at ``/api/holdings``. Never recommends a security —
every response is descriptive (positions/gains/allocation/limits), not advice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.i18n import ws_lang
from ..core.money import Amount
from . import limits as limits_mod
from . import prices as prices_mod
from . import symbols as symbols_mod
from . import trades as trades_mod

router = APIRouter(tags=["holdings"])


class TradeIn(BaseModel):
    date: date
    account: str
    symbol: str
    kind: str  # buy|sell|dividend|interest|contribution
    units: Decimal = Decimal("0")
    price: Amount | None = None
    fees: Amount | None = None
    cash: Amount | None = None
    counter_account: str = "Assets:Bank:Brokerage"
    limit_key: str | None = None


class PriceIn(BaseModel):
    symbol: str
    date: date
    price: Amount
    source: str = "manual"


class PricesFetchIn(BaseModel):
    symbols: list[str] = Field(default_factory=list)


class SymbolIn(BaseModel):
    symbol: str
    name: str
    asset_class: str
    currency: str = "USD"


@router.post("/{ws}/trades")
def api_record_trade(ws: str, body: TradeIn) -> dict:
    try:
        return trades_mod.record_trade(
            ws,
            when=body.date,
            account=body.account,
            symbol=body.symbol,
            units=body.units,
            price=body.price,
            fees=body.fees,
            kind=body.kind,
            counter_account=body.counter_account,
            cash=body.cash,
            limit_key=body.limit_key,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{ws}/trades")
def api_list_trades(ws: str, symbol: str | None = None) -> list[dict]:
    return trades_mod.list_trades(ws, symbol)


@router.get("/{ws}")
def api_get_holdings(
    ws: str, as_of: date | None = None, year: int = 2026, jurisdiction: str = "MX", lang: str | None = None
) -> dict:
    resolved_lang = ws_lang(ws, lang)
    result = trades_mod.positions(ws, as_of, lang=resolved_lang)
    result["contributions"] = trades_mod.contributions_vs_limits(ws, year)
    result["tax_explain"] = trades_mod.tax_explain(jurisdiction, lang=resolved_lang).model_dump(mode="json")
    result["symbols"] = symbols_mod.list_symbols(ws)
    return result


@router.get("/{ws}/explain")
def api_explain(ws: str, jurisdiction: str = "MX", lang: str | None = None) -> dict:
    return trades_mod.tax_explain(jurisdiction, lang=ws_lang(ws, lang)).model_dump(mode="json")


@router.get("/{ws}/limits")
def api_list_limits(ws: str, year: int = 2026) -> list[dict]:
    return limits_mod.list_limits(ws, year)


@router.get("/{ws}/symbols")
def api_list_symbols(ws: str) -> list[dict]:
    return symbols_mod.list_symbols(ws)


@router.post("/{ws}/symbols")
def api_upsert_symbol(ws: str, body: SymbolIn) -> dict:
    return symbols_mod.upsert_symbol(ws, body.symbol, body.name, body.asset_class, body.currency)


@router.post("/{ws}/prices")
def api_record_price(ws: str, body: PriceIn) -> dict:
    return prices_mod.record_price(ws, body.symbol, body.date, body.price, body.source)


@router.get("/{ws}/prices/{symbol}")
def api_list_prices(ws: str, symbol: str) -> list[dict]:
    return prices_mod.list_prices(ws, symbol)


@router.post("/{ws}/prices/fetch")
def api_fetch_prices(ws: str, body: PricesFetchIn) -> dict:
    return prices_mod.fetch_prices(ws, body.symbols)
