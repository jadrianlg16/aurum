"""``holdings_symbols``: symbol -> asset class / currency / name, seeded per workspace."""

from __future__ import annotations

from . import store

# (symbol, name, asset_class, currency) — a starter set covering common MX/US instruments. Anything not
# in this seed can be added per-workspace via the API; this is a convenience default, not a recommendation.
_SEED: list[tuple[str, str, str, str]] = [
    ("CETES", "Cetes (Certificados de la Tesorería)", "bond", "MXN"),
    ("VOO", "Vanguard S&P 500 ETF", "equity", "USD"),
    ("VTI", "Vanguard Total Stock Market ETF", "equity", "USD"),
    ("BTC", "Bitcoin", "crypto", "USD"),
]


def seed_defaults(ws_id: str) -> None:
    conn = store.db()
    (count,) = conn.execute("SELECT COUNT(*) FROM holdings_symbols WHERE ws_id=?", (ws_id,)).fetchone()
    if count:
        return
    for symbol, name, asset_class, currency in _SEED:
        conn.execute(
            "INSERT INTO holdings_symbols (ws_id, symbol, name, asset_class, currency) VALUES (?,?,?,?,?)",
            (ws_id, symbol, name, asset_class, currency),
        )
    conn.commit()


def list_symbols(ws_id: str) -> list[dict]:
    seed_defaults(ws_id)
    conn = store.db()
    rows = conn.execute("SELECT * FROM holdings_symbols WHERE ws_id=? ORDER BY symbol", (ws_id,)).fetchall()
    return [dict(r) for r in rows]


def get_symbol(ws_id: str, symbol: str) -> dict | None:
    seed_defaults(ws_id)
    conn = store.db()
    row = conn.execute(
        "SELECT * FROM holdings_symbols WHERE ws_id=? AND symbol=?", (ws_id, symbol.upper())
    ).fetchone()
    return dict(row) if row else None


def upsert_symbol(ws_id: str, symbol: str, name: str, asset_class: str, currency: str = "USD") -> dict:
    conn = store.db()
    conn.execute(
        "INSERT INTO holdings_symbols (ws_id, symbol, name, asset_class, currency) VALUES (?,?,?,?,?) "
        "ON CONFLICT(ws_id, symbol) DO UPDATE SET name=excluded.name, asset_class=excluded.asset_class, "
        "currency=excluded.currency",
        (ws_id, symbol.upper(), name, asset_class, currency),
    )
    conn.commit()
    return get_symbol(ws_id, symbol)
