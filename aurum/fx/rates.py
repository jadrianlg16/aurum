"""FX rate lookup + conversion.

Lookup order for ``get_rate(base, quote, on)``:

1. same currency -> 1
2. ``fx_rates`` cache, exact (base, quote, date)
3. cache, exact inverse (quote, base, date) -> 1/rate
4. offline fixture directory (``AURUM_FX_FAKE_DIR``), one JSON file per pair: ``BASE_QUOTE.json`` =
   ``{"YYYY-MM-DD": "rate", ...}``. Its inverse file is tried too.
5. Banxico (only for USD<->MXN, only if ``BANXICO_TOKEN`` is set) -- result is cached.
6. nearest date on or before ``on`` from the cache or fixture file (last resort).

Nothing here ever touches the network in tests: point ``AURUM_FX_FAKE_DIR`` at a fixture directory and
leave ``BANXICO_TOKEN`` unset.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..core.config import env
from ..core.money import Amount, q2
from . import store
from .banxico import FxLookupError, fetch_usd_mxn


class FxRateNotFound(LookupError):
    pass


def _fixture_dir() -> Path | None:
    raw = env("AURUM_FX_FAKE_DIR", "")
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else None


def _fixture_lookup(base: str, quote: str, on: date) -> Decimal | None:
    d = _fixture_dir()
    if d is None:
        return None
    direct = d / f"{base}_{quote}.json"
    if direct.exists():
        data = json.loads(direct.read_text(encoding="utf-8"))
        rate = _nearest(data, on)
        if rate is not None:
            return Decimal(str(rate))
    inverse = d / f"{quote}_{base}.json"
    if inverse.exists():
        data = json.loads(inverse.read_text(encoding="utf-8"))
        rate = _nearest(data, on)
        if rate is not None:
            return Decimal("1") / Decimal(str(rate))
    return None


def _nearest(data: dict, on: date) -> str | None:
    """Exact date if present, else the closest date on or before ``on``."""
    if on.isoformat() in data:
        return data[on.isoformat()]
    candidates = sorted(k for k in data if k <= on.isoformat())
    return data[candidates[-1]] if candidates else None


def _cache_lookup(base: str, quote: str, on: date) -> Decimal | None:
    conn = store.db()
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE base=? AND quote=? AND date=?", (base, quote, on.isoformat())
    ).fetchone()
    if row:
        return Decimal(row["rate"])
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE base=? AND quote=? AND date<=? ORDER BY date DESC LIMIT 1",
        (base, quote, on.isoformat()),
    ).fetchone()
    if row:
        return Decimal(row["rate"])
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE base=? AND quote=? AND date<=? ORDER BY date DESC LIMIT 1",
        (quote, base, on.isoformat()),
    ).fetchone()
    if row:
        return Decimal("1") / Decimal(row["rate"])
    return None


def cache_rate(base: str, quote: str, on: date, rate: Decimal, source: str = "manual") -> None:
    conn = store.db()
    conn.execute(
        "INSERT INTO fx_rates (id, base, quote, date, rate, source) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(base, quote, date) DO UPDATE SET rate=excluded.rate, source=excluded.source",
        (store.new_id("fx"), base, quote, on.isoformat(), str(rate), source),
    )
    conn.commit()


def get_rate(base: str, quote: str, on: date | None = None) -> Decimal:
    on = on or date.today()
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal("1")

    cached = _cache_lookup(base, quote, on)
    if cached is not None:
        return cached

    fixture = _fixture_lookup(base, quote, on)
    if fixture is not None:
        return fixture

    if {base, quote} == {"USD", "MXN"}:
        try:
            usd_mxn = fetch_usd_mxn(on)
            cache_rate("USD", "MXN", on, usd_mxn, source="banxico")
            return usd_mxn if base == "USD" else Decimal("1") / usd_mxn
        except FxLookupError:
            pass

    raise FxRateNotFound(f"no FX rate for {base}/{quote} on {on.isoformat()}")


def convert(amount: Amount, to: str, on: date | None = None) -> Amount:
    to = to.upper()
    if amount.currency == to:
        return amount.quantized()
    rate = get_rate(amount.currency, to, on)
    return Amount(amount=q2(amount.amount * rate), currency=to)


def net_worth_in(balances: dict[str, list[Amount]], currency: str, on: date | None = None) -> Amount:
    """Sum every account's amounts (as booked) into a single ``currency`` total, Assets minus Liabilities."""
    total = Decimal("0")
    for account, amounts in balances.items():
        sign = 1 if account.startswith("Assets:") else (-1 if account.startswith("Liabilities:") else 0)
        if sign == 0:
            continue
        for amt in amounts:
            total += sign * convert(amt, currency, on).amount
    return Amount(amount=q2(total), currency=currency)
