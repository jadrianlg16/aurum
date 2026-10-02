"""Banxico SIE (Sistema de Información Económica) client for the USD/MXN FIX rate.

Series id ``SF43718`` is the commonly cited "tipo de cambio FIX" series `(verify)` — Banxico's SIE
catalog should be checked against the current documentation before this drives a filed number; it is
only ever used here as an FX *convenience* rate, never as a tax figure.

Requires ``BANXICO_TOKEN`` (env). Never called in tests — network access is guarded and any failure
(missing token, timeout, non-200, malformed body) raises ``FxLookupError`` so callers can fall back to
the cache or the offline fixture directory.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from ..core.config import env

SERIE_USD_MXN_FIX = "SF43718"  # (verify)
BASE_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"


class FxLookupError(RuntimeError):
    pass


def fetch_usd_mxn(on: date, timeout: float = 5.0) -> Decimal:
    """Fetch the FIX USD/MXN rate for the given date (or the closest prior banking day Banxico has)."""
    token = env("BANXICO_TOKEN", "")
    if not token:
        raise FxLookupError("BANXICO_TOKEN not configured")
    d = on.isoformat()
    url = f"{BASE_URL}/{SERIE_USD_MXN_FIX}/datos/{d}/{d}"
    try:
        resp = httpx.get(url, headers={"Bmx-Token": token}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        datos = payload["bmx"]["series"][0]["datos"]
        if not datos:
            raise FxLookupError(f"no Banxico data for {d}")
        value = datos[-1]["dato"]
        return Decimal(str(value).replace(",", ""))
    except (httpx.HTTPError, KeyError, IndexError, InvalidOperation, ValueError) as e:
        raise FxLookupError(f"Banxico fetch failed: {e}") from e
