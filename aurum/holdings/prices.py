"""Manual and fetched prices, ``holdings_prices``. Offline-safe: ``fetch_prices``
guards ``bean-price``'s absence (not a project dependency) and any network failure, and never raises."""

from __future__ import annotations

from datetime import date

from ..core.money import Amount
from . import store


def record_price(ws_id: str, symbol: str, on: date, price: Amount, source: str = "manual") -> dict:
    conn = store.db()
    conn.execute(
        "INSERT INTO holdings_prices (id, ws_id, symbol, date, price_amount, price_currency, source) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(ws_id, symbol, date) DO UPDATE SET price_amount=excluded.price_amount, "
        "price_currency=excluded.price_currency, source=excluded.source",
        (store.new_id("price"), ws_id, symbol.upper(), on.isoformat(), str(price.amount), price.currency, source),
    )
    conn.commit()
    return latest_price(ws_id, symbol) or {}


def latest_price(ws_id: str, symbol: str, as_of: date | None = None) -> dict | None:
    conn = store.db()
    if as_of:
        row = conn.execute(
            "SELECT * FROM holdings_prices WHERE ws_id=? AND symbol=? AND date<=? ORDER BY date DESC LIMIT 1",
            (ws_id, symbol.upper(), as_of.isoformat()),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM holdings_prices WHERE ws_id=? AND symbol=? ORDER BY date DESC LIMIT 1",
            (ws_id, symbol.upper()),
        ).fetchone()
    return dict(row) if row else None


def list_prices(ws_id: str, symbol: str) -> list[dict]:
    conn = store.db()
    rows = conn.execute(
        "SELECT * FROM holdings_prices WHERE ws_id=? AND symbol=? ORDER BY date", (ws_id, symbol.upper())
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_prices(ws_id: str, symbols: list[str]) -> dict:
    """Try ``beanprice`` sources for each symbol; guarded so an offline test suite never fails here."""
    try:
        from beanprice import price as beanprice_price  # type: ignore
    except ImportError:
        return {"fetched": [], "warnings": ["beanprice is not installed; use manual POST /prices instead"]}

    fetched: list[str] = []
    warnings: list[str] = []
    for symbol in symbols:
        try:
            source = beanprice_price.parse_source_map(f"yahoo/{symbol}")
            _ = source  # pragma: no cover - network fetch intentionally not exercised in tests
            warnings.append(f"{symbol}: beanprice fetch not wired to a live network call in this build")
        except Exception as e:  # network/parse failures must never crash the request
            warnings.append(f"{symbol}: {e}")
    return {"fetched": fetched, "warnings": warnings}
