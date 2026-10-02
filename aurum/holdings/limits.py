"""``holdings_limits`` — contribution limits seeded with ``(verify)`` constants.

Every figure here is a convenience reference for the "contributions vs limits" view, never a filed
number. Values not confirmed against the current-year IRS/SAT text are marked ``verified: False`` and
carry ``(verify)`` in their label; a human pass (or a rule in the registry) should confirm
before any of this drives a computed liability.
"""

from __future__ import annotations

from . import store

# (key, jurisdiction, label, year, amount, currency, verified, law, article, url)
_SEED_2026: list[tuple[str, str, str, int, str, str, bool, str, str, str | None]] = [
    ("401k", "US", "401(k) elective deferral limit (verify)", 2026, "23500", "USD", False,
     "IRC", "§ 402(g)", None),
    ("ira", "US", "Traditional/Roth IRA contribution limit (verify)", 2026, "7000", "USD", False,
     "IRC", "§ 219", None),
    ("hsa_self", "US", "HSA self-only coverage limit (verify)", 2026, "4300", "USD", False,
     "IRC", "§ 223", None),
    ("hsa_family", "US", "HSA family coverage limit (verify)", 2026, "8550", "USD", False,
     "IRC", "§ 223", None),
    ("ppr", "MX", "Aportaciones a plan personal de retiro, tope deducible (verify)", 2026,
     "152331", "MXN", False, "LISR", "151", None),  # (verify) 10% of income or 5 UMA annual, whichever is lower
]


def seed_defaults(ws_id: str, year: int = 2026) -> None:
    conn = store.db()
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM holdings_limits WHERE ws_id=? AND year=?", (ws_id, year)
    ).fetchone()
    if count:
        return
    for key, jurisdiction, label, y, amount, currency, verified, law, article, url in _SEED_2026:
        if y != year:
            continue
        conn.execute(
            "INSERT INTO holdings_limits (ws_id, key, jurisdiction, label, year, amount, currency, "
            "verified, citation_law, citation_article, citation_url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ws_id, key, jurisdiction, label, y, amount, currency, int(verified), law, article, url),
        )
    conn.commit()


def list_limits(ws_id: str, year: int = 2026) -> list[dict]:
    seed_defaults(ws_id, year)
    conn = store.db()
    rows = conn.execute(
        "SELECT * FROM holdings_limits WHERE ws_id=? AND year=? ORDER BY jurisdiction, key", (ws_id, year)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["verified"] = bool(d["verified"])
        out.append(d)
    return out
