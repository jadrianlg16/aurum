"""Trades -> cost-basis lots -> positions/realized gains (FIFO), allocation, contributions vs limits.

FIFO is used for realized-gain lot matching. This is the common US default (IRC § 1012 basis, average
cost is elective for some funds) and a reasonable MX default absent a specific LISR lot-method election
`(verify)` — see docs/modules/holdings.md for the citation gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from ..core.explain import Citation, Explain
from ..core.i18n import t as i18n_t
from ..core.money import Amount, q2
from . import ledger_ext, store
from . import limits as limits_mod
from . import prices as prices_mod
from . import symbols as symbols_mod

VALID_KINDS = {"buy", "sell", "dividend", "interest", "contribution"}


def record_trade(
    ws_id: str,
    *,
    when: date,
    account: str,
    symbol: str,
    units: Decimal,
    price: Amount | None,
    fees: Amount | None,
    kind: str,
    counter_account: str = "Assets:Bank:Brokerage",
    cash: Amount | None = None,
    limit_key: str | None = None,
) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}, expected one of {sorted(VALID_KINDS)}")
    if kind in ("buy", "sell") and (price is None or units <= 0):
        raise ValueError(f"{kind} requires a positive units and a price")
    if kind in ("dividend", "interest", "contribution") and cash is None:
        raise ValueError(f"{kind} requires a cash amount")

    trade_id = store.new_id("trade")
    txn_id = ledger_ext.write_trade_txn(
        ws_id,
        when=when,
        account=account,
        symbol=symbol.upper(),
        kind=kind,
        units=units,
        price=price,
        fees=fees,
        cash=cash,
        counter_account=counter_account,
        trade_id=trade_id,
    )
    conn = store.db()
    conn.execute(
        "INSERT INTO holdings_trades (id, ws_id, date, account, symbol, kind, units, price_amount, "
        "price_currency, fees_amount, fees_currency, cash_amount, cash_currency, counter_account, "
        "limit_key, txn_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            trade_id, ws_id, when.isoformat(), account, symbol.upper(), kind, str(units),
            str(price.amount) if price else None, price.currency if price else None,
            str(fees.amount) if fees else "0", fees.currency if fees else None,
            str(cash.amount) if cash else None, cash.currency if cash else None,
            counter_account, limit_key, txn_id, datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    return get_trade(ws_id, trade_id)


def get_trade(ws_id: str, trade_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM holdings_trades WHERE ws_id=? AND id=?", (ws_id, trade_id)).fetchone()
    if row is None:
        raise KeyError(trade_id)
    return dict(row)


def list_trades(ws_id: str, symbol: str | None = None) -> list[dict]:
    conn = store.db()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM holdings_trades WHERE ws_id=? AND symbol=? ORDER BY date, created_at",
            (ws_id, symbol.upper()),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM holdings_trades WHERE ws_id=? ORDER BY date, created_at", (ws_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@dataclass
class _Lot:
    units: Decimal
    cost_per_unit: Decimal
    currency: str
    opened: date


@dataclass
class _SymbolState:
    lots: list[_Lot] = field(default_factory=list)
    realized: list[dict] = field(default_factory=list)
    account: str = ""


def _fifo(ws_id: str, symbol: str, as_of: date | None) -> _SymbolState:
    state = _SymbolState()
    for t in list_trades(ws_id, symbol):
        t_date = date.fromisoformat(t["date"])
        if as_of and t_date > as_of:
            continue
        if t["kind"] == "buy":
            state.account = t["account"]
            state.lots.append(
                _Lot(
                    units=Decimal(t["units"]),
                    cost_per_unit=Decimal(t["price_amount"]) + (Decimal(t["fees_amount"] or "0") / Decimal(t["units"])),
                    currency=t["price_currency"],
                    opened=t_date,
                )
            )
        elif t["kind"] == "sell":
            remaining = Decimal(t["units"])
            sell_price = Decimal(t["price_amount"])
            currency = t["price_currency"]
            while remaining > 0 and state.lots:
                lot = state.lots[0]
                matched = min(lot.units, remaining)
                proceeds = matched * sell_price
                cost = matched * lot.cost_per_unit
                state.realized.append(
                    {
                        "date": t["date"],
                        "symbol": symbol.upper(),
                        "units": str(matched),
                        "proceeds": str(q2(proceeds)),
                        "cost": str(q2(cost)),
                        "gain": str(q2(proceeds - cost)),
                        "currency": currency,
                        "lot_opened": lot.opened.isoformat(),
                        "holding_period_days": (t_date - lot.opened).days,
                    }
                )
                lot.units -= matched
                remaining -= matched
                if lot.units <= 0:
                    state.lots.pop(0)
            # remaining > 0 here means a sell with no matching lot (data error) — ignored, not fabricated.
    return state


def positions(ws_id: str, as_of: date | None = None, lang: str = "es") -> dict:
    conn = store.db()
    symbols = [r["symbol"] for r in conn.execute(
        "SELECT DISTINCT symbol FROM holdings_trades WHERE ws_id=? AND kind IN ('buy','sell')", (ws_id,)
    ).fetchall()]

    out_positions: list[dict] = []
    all_realized: list[dict] = []
    allocation: dict[str, Decimal] = {}
    total_market_value = Decimal("0")

    for symbol in sorted(symbols):
        state = _fifo(ws_id, symbol, as_of)
        all_realized.extend(state.realized)
        units_held = sum((lot.units for lot in state.lots), Decimal("0"))
        if units_held <= 0:
            continue
        cost_basis = sum((lot.units * lot.cost_per_unit for lot in state.lots), Decimal("0"))
        currency = state.lots[0].currency if state.lots else "USD"
        price_row = prices_mod.latest_price(ws_id, symbol, as_of)
        market_value = units_held * Decimal(price_row["price_amount"]) if price_row else None
        unrealized = (market_value - cost_basis) if market_value is not None else None
        sym_meta = symbols_mod.get_symbol(ws_id, symbol) or {"asset_class": "other", "name": symbol}
        out_positions.append(
            {
                "symbol": symbol,
                "account": state.account,
                "units": str(units_held),
                "cost_basis": {"amount": str(q2(cost_basis)), "currency": currency},
                "market_value": {"amount": str(q2(market_value)), "currency": currency}
                if market_value is not None
                else None,
                "unrealized_gain": {"amount": str(q2(unrealized)), "currency": currency}
                if unrealized is not None
                else None,
                "asset_class": sym_meta.get("asset_class", "other"),
                "name": sym_meta.get("name", symbol),
                "price_as_of": price_row["date"] if price_row else None,
            }
        )
        if market_value is not None:
            allocation[sym_meta.get("asset_class", "other")] = allocation.get(
                sym_meta.get("asset_class", "other"), Decimal("0")
            ) + market_value
            total_market_value += market_value

    allocation_pct = {
        cls: str(q2(amt / total_market_value * 100)) if total_market_value else "0.00"
        for cls, amt in allocation.items()
    }

    explain = Explain(
        summary=i18n_t("holdings.positions.summary", lang),
        citations=[
            Citation(law="LISR", article="129/133/150", trust_tier="primary", excerpt="(verify)"),
            Citation(law="IRC", article="§ 1(h) / § 1222", trust_tier="primary", excerpt="(verify)"),
        ],
    )
    explain.add_step("total_market_value", str(q2(total_market_value)))
    return {
        "positions": out_positions,
        "realized_gains": all_realized,
        "allocation": {"by_asset_class": allocation_pct, "total_market_value": str(q2(total_market_value))},
        "explain": explain.model_dump(mode="json"),
    }


def contributions_vs_limits(ws_id: str, year: int) -> dict:
    conn = store.db()
    rows = conn.execute(
        "SELECT limit_key, cash_amount, cash_currency FROM holdings_trades "
        "WHERE ws_id=? AND kind='contribution' AND limit_key IS NOT NULL AND substr(date,1,4)=?",
        (ws_id, str(year)),
    ).fetchall()
    totals: dict[str, Decimal] = {}
    currencies: dict[str, str] = {}
    for r in rows:
        totals[r["limit_key"]] = totals.get(r["limit_key"], Decimal("0")) + Decimal(r["cash_amount"] or "0")
        currencies[r["limit_key"]] = r["cash_currency"] or "USD"

    out = []
    for limit in limits_mod.list_limits(ws_id, year):
        key = limit["key"]
        contributed = totals.get(key, Decimal("0"))
        cap = Decimal(limit["amount"])
        out.append(
            {
                "key": key,
                "jurisdiction": limit["jurisdiction"],
                "label": limit["label"],
                "limit": {"amount": str(cap), "currency": limit["currency"]},
                "contributed": {"amount": str(q2(contributed)), "currency": currencies.get(key, limit["currency"])},
                "remaining": {"amount": str(q2(cap - contributed)), "currency": limit["currency"]},
                "verified": limit["verified"],
            }
        )
    return {"year": year, "limits": out}


def tax_explain(jurisdiction: str, lang: str = "es") -> Explain:
    if jurisdiction.upper() == "MX":
        return Explain(
            summary=i18n_t("holdings.tax_explain.mx.summary", lang),
            citations=[
                Citation(law="LISR", article="129", trust_tier="primary", excerpt="(verify) enajenación de acciones"),
                Citation(law="LISR", article="133", trust_tier="primary", excerpt="(verify) intereses"),
                Citation(law="LISR", article="150", trust_tier="primary", excerpt="(verify) declaración anual"),
            ],
            confidence=0.4,
        )
    return Explain(
        summary=i18n_t("holdings.tax_explain.us.summary", lang),
        citations=[
            Citation(law="IRC", article="§ 1(h)", trust_tier="primary", excerpt="(verify) capital gains rates"),
            Citation(law="IRC", article="§ 1222", trust_tier="primary", excerpt="(verify) definitions: short/long-term"),
        ],
        confidence=0.4,
    )
