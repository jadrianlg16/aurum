"""Synthetic business demo workspace ``demo-biz`` — a persona moral in Nuevo León, one quarter.

Everything here is fake (synthetic fixtures only): RFCs are SAT's own generic placeholders and invented
demo patterns, and no real client, employee or CFDI ever enters this repo.

The quarter is 2026-04 … 2026-06 and is designed so every business endpoint has something to show:

* **3 employees** at different SBCs, so the cesantía bracket and the ISR tarifa differ per row.
* **8 CFDI emitidos** — a mix of PUE (collected on issue) and PPD (two with a REP, two without), so
  ``/invoices`` reports real aging buckets and a DSO above zero.
* **COGS and opex postings** in every month, plus an opening cash balance, so ``/kpis`` reports a gross
  margin, an opex breakdown and a runway.

This builder is standalone; ``aurum.demo.extras`` calls it when the demo workspaces are built.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..core.db import connect
from ..core.money import Amount, q2
from ..core.workspaces import Workspace, save_workspace
from ..ledger.base import Posting, Transaction, get_ledger
from .chart import apply_business_template
from .payroll import add_employee, run_payroll

WS_ID = "demo-biz"
RFC = "XAXX010101000"  # SAT's generic placeholder — safe as a synthetic own-RFC
CURRENCY = "MXN"
PERIODS = ["2026-04", "2026-05", "2026-06"]
IVA = Decimal("0.16")

CLIENTS = [
    ("DPM010101AA1", "Cliente Alfa SA de CV"),
    ("DPM020202BB2", "Cliente Beta SA de CV"),
    ("DPF030303CC3", "Cliente Gamma"),
]

# (uuid suffix, issue date, client index, subtotal, metodo_pago, rep_date or None)
INVOICES: list[tuple[str, date, int, str, str, date | None]] = [
    ("0001", date(2026, 4, 6), 0, "120000.00", "PUE", None),
    ("0002", date(2026, 4, 20), 1, "85000.00", "PPD", date(2026, 5, 12)),
    ("0003", date(2026, 5, 5), 2, "42000.00", "PUE", None),
    ("0004", date(2026, 5, 15), 0, "150000.00", "PPD", date(2026, 6, 10)),
    ("0005", date(2026, 5, 26), 1, "64000.00", "PPD", None),  # unpaid, ages into 31-60
    ("0006", date(2026, 6, 3), 2, "38000.00", "PUE", None),
    ("0007", date(2026, 6, 12), 0, "96000.00", "PPD", None),  # unpaid, 0-30
    ("0008", date(2026, 3, 9), 1, "58000.00", "PPD", None),  # unpaid, 90+
]

EMPLOYEES = [
    # (name, daily salary, SBC — SBC is higher because it integrates aguinaldo and prima vacacional
    ("Empleada Demo Uno", "450.00", "480.00"),
    ("Empleado Demo Dos", "980.00", "1045.00"),
    ("Empleada Demo Tres", "315.04", "336.00"),
]

# (month index, account, amount) — COGS and opex, booked mid-month against the bank.
COGS = [
    (0, "Expenses:COGS:Materials", "48000.00"),
    (0, "Expenses:COGS:Subcontractors", "18000.00"),
    (1, "Expenses:COGS:Materials", "61000.00"),
    (1, "Expenses:COGS:Freight", "7500.00"),
    (2, "Expenses:COGS:Materials", "39000.00"),
    (2, "Expenses:COGS:Subcontractors", "12000.00"),
]
OPEX = [
    (0, "Expenses:Opex:Rent", "28000.00"),
    (0, "Expenses:Opex:Utilities", "6200.00"),
    (0, "Expenses:Opex:Software", "4300.00"),
    (1, "Expenses:Opex:Rent", "28000.00"),
    (1, "Expenses:Opex:Marketing", "15000.00"),
    (1, "Expenses:Opex:Professional", "9500.00"),
    (2, "Expenses:Opex:Rent", "28000.00"),
    (2, "Expenses:Opex:Utilities", "5800.00"),
    (2, "Expenses:Opex:Office", "3100.00"),
]

OPENING_CASH = "450000.00"


def _period_date(index: int, day: int) -> date:
    year, month = (int(x) for x in PERIODS[index].split("-"))
    return date(year, month, day)


def _amount(value: str) -> Amount:
    return Amount(amount=q2(Decimal(value)), currency=CURRENCY)


def _store_cfdi(ws_id: str, suffix: str, fecha: date, client: tuple[str, str], subtotal: Decimal, metodo: str) -> str:
    """Write one issued CFDI straight into ``ingest_cfdi`` (the ingest module's own table)."""
    uuid = f"DEMO-BIZ-0000-0000-{suffix}"
    iva = q2(subtotal * IVA)
    total = q2(subtotal + iva)
    doc = {
        "uuid": uuid,
        "version": "4.0",
        "tipo": "I",
        "fecha": datetime.combine(fecha, datetime.min.time()).isoformat(),
        "emisor_rfc": RFC,
        "receptor_rfc": client[0],
        "receptor_nombre": client[1],
        "subtotal": str(subtotal),
        "total": str(total),
        "moneda": CURRENCY,
        "metodo_pago": metodo,
        "iva_trasladado": str(iva),
        "direction": "emitido",
        "synthetic": True,
    }
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_cfdi (uuid, ws_id, tipo, direction, fecha, emisor_rfc, receptor_rfc, "
            "subtotal, total, moneda, metodo_pago, forma_pago, uso_cfdi, iva_trasladado, impuestos_retenidos, "
            "raw_path, json, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uuid,
                ws_id,
                "I",
                "emitido",
                doc["fecha"],
                RFC,
                client[0],
                str(subtotal),
                str(total),
                CURRENCY,
                metodo,
                "03" if metodo == "PUE" else "99",
                "G03",
                str(iva),
                "0",
                None,
                json.dumps(doc, ensure_ascii=False),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return uuid


def _store_rep(ws_id: str, invoice_uuid: str, suffix: str, fecha_pago: date, total: Decimal) -> None:
    """A complemento de pago (tipo P) plus its DoctoRelacionado row."""
    rep_uuid = f"DEMO-BIZ-REP0-0000-{suffix}"
    doc = {
        "uuid": rep_uuid,
        "tipo": "P",
        "fecha": datetime.combine(fecha_pago, datetime.min.time()).isoformat(),
        "emisor_rfc": RFC,
        "direction": "emitido",
        "synthetic": True,
    }
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_cfdi (uuid, ws_id, tipo, direction, fecha, emisor_rfc, receptor_rfc, "
            "subtotal, total, moneda, metodo_pago, forma_pago, uso_cfdi, iva_trasladado, impuestos_retenidos, "
            "raw_path, json, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rep_uuid,
                ws_id,
                "P",
                "emitido",
                doc["fecha"],
                RFC,
                "",
                "0",
                "0",
                CURRENCY,
                None,
                None,
                "CP01",
                "0",
                "0",
                None,
                json.dumps(doc, ensure_ascii=False),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        conn.execute(
            "INSERT INTO ingest_cfdi_pagos (uuid_pago, ws_id, fecha_pago, monto, uuid_relacionado, imp_pagado) "
            "VALUES (?,?,?,?,?,?)",
            (rep_uuid, ws_id, fecha_pago.isoformat(), str(total), invoice_uuid, str(total)),
        )
        conn.commit()
    finally:
        conn.close()


def build_demo_biz(data_dir: str | Path | None = None) -> dict[str, Any]:
    """Create the ``demo-biz`` workspace and everything in it. Idempotent per data dir."""
    if data_dir is not None:
        import os

        # ``settings()`` reads the environment fresh on every call, so setting it is enough.
        os.environ["AURUM_DATA_DIR"] = str(data_dir)
        from ..core import db as db_mod

        db_mod.reset_for_tests()

    ws = save_workspace(
        Workspace(
            id=WS_ID,
            name="Demo Persona Moral (NL)",
            kind="business",
            jurisdictions=["MX"],
            base_currency=CURRENCY,
            language="es",
            profile={
                "rfc": RFC,
                "regime": "GENERAL_PM",
                "state": "NL",
                "entity": "persona_moral",
                "synthetic": True,
            },
        )
    )
    accounts = apply_business_template(WS_ID, "mx_persona_moral", CURRENCY)
    ledger = get_ledger()

    ledger.append(
        WS_ID,
        Transaction(
            date=date(2026, 3, 31),
            narration="Saldo inicial demo",
            postings=[
                Posting(account="Assets:Bank:BBVA", amount=_amount(OPENING_CASH)),
                Posting(account="Equity:Opening-Balances", amount=None),
            ],
            meta={"source": "demo_biz"},
        ),
    )

    invoice_uuids: list[str] = []
    for suffix, fecha, client_ix, subtotal_s, metodo, rep_date in INVOICES:
        client = CLIENTS[client_ix]
        subtotal = Decimal(subtotal_s)
        iva = q2(subtotal * IVA)
        total = q2(subtotal + iva)
        uuid = _store_cfdi(WS_ID, suffix, fecha, client, subtotal, metodo)
        invoice_uuids.append(uuid)
        ledger.append(
            WS_ID,
            Transaction(
                date=fecha,
                payee=client[1],
                narration=f"Factura {suffix}",
                postings=[
                    Posting(account="Assets:Receivable:Clients", amount=Amount(amount=total, currency=CURRENCY)),
                    Posting(account="Income:Sales:Services", amount=Amount(amount=-subtotal, currency=CURRENCY)),
                    Posting(
                        account="Liabilities:Taxes:IVA-Trasladado", amount=Amount(amount=-iva, currency=CURRENCY)
                    ),
                ],
                meta={"source": "demo_biz", "cfdi_uuid": uuid, "metodo_pago": metodo},
            ),
        )
        collected_on = fecha if metodo == "PUE" else rep_date
        if metodo == "PPD" and rep_date is not None:
            _store_rep(WS_ID, uuid, suffix, rep_date, total)
        if collected_on is not None:
            ledger.append(
                WS_ID,
                Transaction(
                    date=collected_on,
                    payee=client[1],
                    narration=f"Cobro factura {suffix}",
                    postings=[
                        Posting(account="Assets:Bank:BBVA", amount=Amount(amount=total, currency=CURRENCY)),
                        Posting(
                            account="Assets:Receivable:Clients", amount=Amount(amount=-total, currency=CURRENCY)
                        ),
                    ],
                    meta={"source": "demo_biz", "cfdi_uuid": uuid},
                ),
            )

    for month_ix, account, amount_s in COGS + OPEX:
        when = _period_date(month_ix, 14)
        amount = _amount(amount_s)
        iva = Amount(amount=q2(amount.amount * IVA), currency=CURRENCY)
        ledger.append(
            WS_ID,
            Transaction(
                date=when,
                payee="Proveedor Demo SA de CV",
                narration=account.split(":")[-1],
                postings=[
                    Posting(account=account, amount=amount),
                    Posting(account="Assets:Taxes:IVA-Acreditable", amount=iva),
                    Posting(account="Assets:Bank:BBVA", amount=None),
                ],
                meta={"source": "demo_biz"},
            ),
        )

    employees = [
        add_employee(WS_ID, name=name, daily_salary=daily, sbc_daily=sbc, state="NL", currency=CURRENCY)
        for name, daily, sbc in EMPLOYEES
    ]
    runs = [run_payroll(WS_ID, period) for period in PERIODS]

    return {
        "workspace": ws.masked(),
        "accounts": len(accounts),
        "periods": PERIODS,
        "invoices": invoice_uuids,
        "employees": employees,
        "payroll_runs": [{"id": r["id"], "period": r["period"], "totals": r["totals"]} for r in runs],
    }


if __name__ == "__main__":  # pragma: no cover - manual seeding
    import sys

    result = build_demo_biz(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
