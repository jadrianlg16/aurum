"""Invoicing register: CFDI emitidos, issued vs paid, aging, top clients, DSO.

Reads ``ingest_cfdi`` / ``ingest_cfdi_pagos`` **defensively** — the ingest module owns those tables and
this module must keep working when they are empty, when a column is missing (an older schema), or when
the whole ingest module is absent. Nothing is written here.

Payment rules follow the same cash basis the tax module uses (SAT's prefill rules):

* **PUE** — treated as collected on ``fecha`` (SAT's prefill assumption).
* **PPD** — collected only through a REP (a ``tipo="P"`` CFDI) whose ``DoctoRelacionado`` points back
  at the invoice; the collected amount is the sum of its ``imp_pagado``.

Aging is measured from the invoice date to the ``as_of`` date, on the *unpaid* balance only. RFCs are
masked in every response; the reminder text names the client only by masked RFC unless the caller
passes a display name.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..core.db import connect
from ..core.explain import Explain
from ..core.i18n import t
from ..core.money import q2

CURRENCY = "MXN"
BUCKETS = ("0-30", "31-60", "61-90", "90+")


def mask_rfc(rfc: str | None) -> str:
    if not rfc:
        return "***"
    return "*" * max(len(rfc) - 4, 0) + rfc[-4:]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:  # pragma: no cover - defensive
        return set()


def _dec(value: Any, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:  # pragma: no cover - defensive against bad stored rows
        return Decimal(default)


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def load_emitidos(ws_id: str, start: date | None = None, end: date | None = None) -> list[dict[str, Any]]:
    """Every issued invoice (``tipo='I'``, ``direction='emitido'``) with its payments attached."""
    conn = connect()
    try:
        if not _table_exists(conn, "ingest_cfdi"):
            return []
        cols = _columns(conn, "ingest_cfdi")
        needed = {"uuid", "ws_id", "tipo", "direction", "fecha", "total"}
        if not needed <= cols:
            return []
        rows = conn.execute(
            "SELECT * FROM ingest_cfdi WHERE ws_id=? AND direction='emitido' AND tipo='I' ORDER BY fecha",
            (ws_id,),
        ).fetchall()
        pagos: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if _table_exists(conn, "ingest_cfdi_pagos"):
            for p in conn.execute(
                "SELECT uuid_relacionado, fecha_pago, imp_pagado FROM ingest_cfdi_pagos WHERE ws_id=?",
                (ws_id,),
            ).fetchall():
                pagos[p["uuid_relacionado"]].append(dict(p))
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        fecha = _as_date(r.get("fecha"))
        if fecha is None:
            continue
        if start and fecha < start:
            continue
        if end and fecha > end:
            continue
        total = q2(_dec(r.get("total")))
        metodo = (r.get("metodo_pago") or "").upper() or None
        reps = pagos.get(r["uuid"], [])
        if metodo == "PUE":
            paid = total
            paid_on = fecha
        else:
            paid = q2(sum((_dec(p.get("imp_pagado")) for p in reps), Decimal("0")))
            paid_dates = [d for d in (_as_date(p.get("fecha_pago")) for p in reps) if d]
            paid_on = max(paid_dates) if paid_dates and paid >= total else None
        out.append(
            {
                "uuid": r["uuid"],
                "fecha": fecha,
                "receptor_rfc": r.get("receptor_rfc") or "",
                "total": total,
                "subtotal": q2(_dec(r.get("subtotal"))),
                "moneda": r.get("moneda") or CURRENCY,
                "metodo_pago": metodo,
                "paid": min(paid, total),
                "outstanding": q2(max(total - paid, Decimal("0"))),
                "paid_on": paid_on,
                "reps": len(reps),
                "client_name": _client_name(r),
            }
        )
    return out


def _client_name(row: dict[str, Any]) -> str | None:
    """Best-effort receptor name from the stored CFDI JSON, without assuming it is there."""
    raw = row.get("json")
    if not raw:
        return None
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        return None
    for key in ("receptor_nombre", "receptor_name"):
        if isinstance(doc.get(key), str):
            return doc[key]
    receptor = doc.get("receptor")
    if isinstance(receptor, dict):
        for key in ("nombre", "Nombre", "name"):
            if isinstance(receptor.get(key), str):
                return receptor[key]
    return None


def bucket_for(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def register(
    ws_id: str,
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
    currency: str = CURRENCY,
    lang: str = "es",
) -> dict[str, Any]:
    """Issued vs paid, aging buckets, top clients and DSO for the workspace's issued CFDIs."""
    as_of = as_of or end or date.today()
    invoices = load_emitidos(ws_id, start, end)
    issued = q2(sum((i["total"] for i in invoices), Decimal("0")))
    collected = q2(sum((i["paid"] for i in invoices), Decimal("0")))
    outstanding = q2(sum((i["outstanding"] for i in invoices), Decimal("0")))

    aging = {b: Decimal("0") for b in BUCKETS}
    aging_count = {b: 0 for b in BUCKETS}
    open_invoices: list[dict[str, Any]] = []
    for inv in invoices:
        if inv["outstanding"] <= 0:
            continue
        age = (as_of - inv["fecha"]).days
        bucket = bucket_for(age)
        aging[bucket] += inv["outstanding"]
        aging_count[bucket] += 1
        open_invoices.append(
            {
                "uuid": inv["uuid"],
                "fecha": inv["fecha"].isoformat(),
                "client_rfc": mask_rfc(inv["receptor_rfc"]),
                "metodo_pago": inv["metodo_pago"],
                "total": {"amount": str(inv["total"]), "currency": inv["moneda"]},
                "outstanding": {"amount": str(inv["outstanding"]), "currency": inv["moneda"]},
                "age_days": age,
                "bucket": bucket,
                "reps": inv["reps"],
            }
        )

    by_client: dict[str, dict[str, Any]] = {}
    for inv in invoices:
        entry = by_client.setdefault(
            inv["receptor_rfc"],
            {"issued": Decimal("0"), "paid": Decimal("0"), "outstanding": Decimal("0"), "count": 0},
        )
        entry["issued"] += inv["total"]
        entry["paid"] += inv["paid"]
        entry["outstanding"] += inv["outstanding"]
        entry["count"] += 1
    top_clients = [
        {
            "client_rfc": mask_rfc(rfc),
            "invoices": v["count"],
            "issued": {"amount": str(q2(v["issued"])), "currency": currency},
            "paid": {"amount": str(q2(v["paid"])), "currency": currency},
            "outstanding": {"amount": str(q2(v["outstanding"])), "currency": currency},
        }
        for rfc, v in sorted(by_client.items(), key=lambda kv: kv[1]["issued"], reverse=True)
    ][:10]

    dso, dso_formula = _dso(invoices, issued, outstanding, start, end, as_of, lang=lang)

    explain = Explain(
        summary=t(
            "business.invoices.register.summary",
            lang,
            issued=issued,
            currency=currency,
            collected=collected,
            outstanding=outstanding,
            as_of=as_of.isoformat(),
            dso=dso,
        ),
        rule_versions=[],
    )
    explain.add_step(t("business.invoices.register.step.cfdi_issued", lang), len(invoices))
    explain.add_step(t("business.invoices.register.step.total_issued", lang), issued)
    explain.add_step(
        t("business.invoices.register.step.collected", lang), collected, formula=t("business.invoices.register.step.collected_formula", lang)
    )
    explain.add_step(t("business.invoices.register.step.outstanding", lang), outstanding, formula=f"{issued} − {collected}")
    for b in BUCKETS:
        explain.add_step(
            t("business.invoices.register.step.aging_bucket", lang, bucket=b),
            q2(aging[b]),
            formula=t("business.invoices.register.step.aging_formula", lang, count=aging_count[b]),
        )
    explain.add_step(t("business.invoices.register.step.dso", lang), dso, formula=dso_formula)

    return {
        "workspace": ws_id,
        "as_of": as_of.isoformat(),
        "currency": currency,
        "period": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        "counts": {"issued": len(invoices), "open": len(open_invoices)},
        "issued": {"amount": str(issued), "currency": currency},
        "collected": {"amount": str(collected), "currency": currency},
        "outstanding": {"amount": str(outstanding), "currency": currency},
        "aging": [
            {
                "bucket": b,
                "amount": {"amount": str(q2(aging[b])), "currency": currency},
                "invoices": aging_count[b],
            }
            for b in BUCKETS
        ],
        "open_invoices": sorted(open_invoices, key=lambda i: i["age_days"], reverse=True),
        "top_clients": top_clients,
        "dso_days": str(dso),
        "explain": explain.model_dump(mode="json"),
    }


def _dso(
    invoices: list[dict[str, Any]],
    issued: Decimal,
    outstanding: Decimal,
    start: date | None,
    end: date | None,
    as_of: date,
    lang: str = "es",
) -> tuple[Decimal, str]:
    """Classic DSO = receivables ÷ credit sales × days in the window."""
    if issued <= 0 or not invoices:
        return Decimal("0"), t("business.invoices.dso.no_sales", lang)
    first = start or min(i["fecha"] for i in invoices)
    last = end or as_of
    days = Decimal(max((last - first).days + 1, 1))
    dso = (outstanding / issued * days).quantize(Decimal("1"))
    return dso, f"({outstanding} ÷ {issued}) × {days} días"


REMINDER_ES = (
    "Estimado cliente {client}:\n\n"
    "Le recordamos que la factura {uuid} del {fecha} por {total} {currency} presenta un saldo pendiente "
    "de {outstanding} {currency} con {age} días de antigüedad.\n"
    "Agradeceremos su pago o, si ya fue realizado, el comprobante correspondiente para conciliarlo.\n\n"
    "Quedamos a sus órdenes."
)
REMINDER_EN = (
    "Dear {client},\n\n"
    "This is a reminder that invoice {uuid} dated {fecha} for {total} {currency} still shows an "
    "outstanding balance of {outstanding} {currency}, {age} days past its issue date.\n"
    "We would appreciate payment or, if it has already been made, the payment record so we can "
    "reconcile it.\n\n"
    "Kind regards."
)


def reminder(
    ws_id: str,
    uuid: str,
    as_of: date | None = None,
    client_name: str | None = None,
) -> dict[str, Any]:
    """Bilingual reminder text for one unpaid invoice. **Nothing is sent** — the caller copies it."""
    as_of = as_of or date.today()
    invoices = {i["uuid"]: i for i in load_emitidos(ws_id)}
    inv = invoices.get(uuid)
    if inv is None:
        raise KeyError(uuid)
    age = (as_of - inv["fecha"]).days
    fields = {
        "client": client_name or inv["client_name"] or mask_rfc(inv["receptor_rfc"]),
        "uuid": inv["uuid"],
        "fecha": inv["fecha"].isoformat(),
        "total": str(inv["total"]),
        "outstanding": str(inv["outstanding"]),
        "currency": inv["moneda"],
        "age": age,
    }
    return {
        "uuid": inv["uuid"],
        "client_rfc": mask_rfc(inv["receptor_rfc"]),
        "outstanding": {"amount": str(inv["outstanding"]), "currency": inv["moneda"]},
        "age_days": age,
        "bucket": bucket_for(age),
        "paid": inv["outstanding"] <= 0,
        "text": {"es": REMINDER_ES.format(**fields), "en": REMINDER_EN.format(**fields)},
        "sent": False,
        "note": "Aurum never sends messages; copy this text into your own email or WhatsApp.",
    }
