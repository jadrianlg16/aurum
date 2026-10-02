"""Demo extras: register the demo CFDIs in the ingest table and seed the pf tables.

`generate.py` builds the workspace, XMLs, bank CSVs and ledger. This module makes the same workspace
visible to the Documents screen (``ingest_cfdi``) and the Plan/Home screens (labels, budgets, goals, a
credit card, a loan). Everything is idempotent and defensive: if another module is
missing, its part is skipped and reported.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def register_cfdis(ws_id: str, cfdi_dir: Path, workspace_rfc: str) -> int:
    from ..ingest.cfdi import parse_cfdi_xml
    from ..ingest.router import _store_cfdi

    n = 0
    for xml in sorted(cfdi_dir.glob("*.xml")):
        doc = parse_cfdi_xml(xml.read_bytes(), workspace_rfc, raw_path=str(xml))
        _store_cfdi(ws_id, doc)
        n += 1
    return n


def register_bank_lines(ws_id: str, bank_dir: Path, bank: str = "BBVA", currency: str = "MXN") -> int:
    """Insert the demo bank CSV rows into ``ingest_bank_lines`` (no Inbox items: the ledger already has them),
    so the Reconcile board has lines to match against ledger transactions and CFDIs."""
    import csv
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from ..core.db import connect
    from ..ingest.bank_csv import line_hash

    n = 0
    conn = connect()
    try:
        for path in sorted(bank_dir.glob("*.csv")):
            with path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    d = date.fromisoformat(row["Fecha"])
                    amount = Decimal(row.get("Abono") or "0") - Decimal(row.get("Cargo") or "0")
                    desc = row["Descripcion"]
                    conn.execute(
                        "INSERT OR IGNORE INTO ingest_bank_lines (ws_id, bank, date, description, amount, currency, "
                        "balance, hash, imported_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (ws_id, bank, d.isoformat(), desc, str(amount), currency, None,
                         line_hash(ws_id, bank, d, desc, amount), datetime.now(UTC).isoformat(timespec="seconds")),
                    )
                    n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def seed_pf(ws_id: str, period: str, currency: str = "MXN") -> dict[str, int]:
    from ..pf import budgets, credit, goals, labels

    labels.seed_defaults(ws_id)
    by_name = {lbl["name"].lower(): lbl for lbl in labels.list_labels(ws_id)}
    counts = {"labels": len(by_name), "budgets": 0, "goals": 0, "cards": 0, "loans": 0}

    if not budgets.list_budgets(ws_id):
        for name, amount in (("comida fuera", "3500"), ("súper", "6000")):
            lbl = by_name.get(name) or next(iter(by_name.values()))
            budgets.create_budget(
                ws_id, budgets.Budget(label_id=lbl["id"], period=period, amount=amount, currency=currency, rollover=True)
            )
            counts["budgets"] += 1

    if not goals.list_goals(ws_id):
        goals.create_goal(
            ws_id,
            goals.Goal(
                kind="emergency", name="Fondo de emergencia", target="90000", currency=currency,
                target_date="2027-06-30", account="Assets:Bank:Nu",
            ),
        )
        goals.create_goal(
            ws_id,
            goals.Goal(
                kind="purchase", name="Laptop nueva", target="35000", currency=currency,
                target_date="2026-12-31", account="Assets:Bank:Banorte",
            ),
        )
        counts["goals"] = 2

    if not credit.list_cards(ws_id):
        credit.create_card(
            ws_id,
            credit.CreditCard(
                account="Liabilities:CreditCard:BBVA", name="BBVA Azul", cut_day=20, due_day=10,
                limit_amount="60000", currency=currency, apr="0.42",
            ),
        )
        counts["cards"] = 1

    if not credit.list_loans(ws_id):
        credit.create_loan(
            ws_id,
            credit.Loan(
                account="Liabilities:Loans:Auto", name="Crédito auto", principal="180000", currency=currency,
                annual_rate="0.14", months=48, start="2026-01-15",
            ),
        )
        counts["loans"] = 1
    return counts


def register_pf_accounts(ws_id: str = "demo-mx") -> dict[str, Any]:
    """Make ``demo-mx``'s existing ledger accounts show up in the "Mi dinero" personal screens:
    three ``pf_accounts`` rows keyed on ``(ws_id, account)`` via
    ``INSERT OR IGNORE`` against the real ledger account strings the demo already posts to — no ledger
    append, so ``tests/demo/test_demo_workspace.py``'s pinned balances never move. Also re-points the
    two demo goals at those real accounts (``goals.update_goal`` unconditionally, since ``seed_pf``
    skips goal creation once any exist) — the auto loan stays on ``Liabilities:Loans:Auto``."""
    from ..core.db import connect

    ts = datetime.now(UTC).isoformat(timespec="seconds")
    rows = [
        # (name, type, ledger account, institution, credit_limit, cut_day, due_day, apr)
        ("BBVA", "checking", "Assets:Bank:BBVA", "BBVA", None, None, None, None),
        ("Efectivo", "cash", "Assets:Cash", None, None, None, None, None),
        ("Tarjeta BBVA", "credit_card", "Liabilities:CreditCard:BBVA", "BBVA", "60000", 20, 10, "0.42"),
    ]
    conn = connect()
    created = 0
    try:
        for name, type_, account, institution, limit, cut_day, due_day, apr in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO pf_accounts (id, ws_id, name, type, institution, currency, account, "
                "credit_limit, cut_day, due_day, apr, archived, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (f"acct-{uuid.uuid4().hex[:12]}", ws_id, name, type_, institution, "MXN", account, limit,
                 cut_day, due_day, apr, ts, ts),
            )
            created += cur.rowcount
        conn.commit()
    finally:
        conn.close()

    from ..pf import goals as pf_goals

    repoint = {"Fondo de emergencia": "Assets:Bank:BBVA", "Laptop nueva": "Assets:Cash"}
    repointed = 0
    for goal in pf_goals.list_goals(ws_id):
        target = repoint.get(goal["name"])
        if target and goal.get("account") != target:
            pf_goals.update_goal(
                ws_id, goal["id"],
                pf_goals.Goal(
                    kind=goal["kind"], name=goal["name"], target=goal["target"], currency=goal["currency"],
                    target_date=goal.get("target_date"), account=target,
                ),
            )
            repointed += 1
    return {"accounts_created": created, "goals_repointed": repointed}


def seed_extras(ws_id: str, ws_dir: Path, workspace_rfc: str, period: str, currency: str = "MXN") -> dict[str, Any]:
    report: dict[str, Any] = {}
    try:
        report["cfdi_registered"] = register_cfdis(ws_id, ws_dir / "docs" / "cfdi", workspace_rfc)
    except Exception as e:  # noqa: BLE001 — ingest module absent or changed; demo must still build
        report["cfdi_registered"] = f"skipped: {type(e).__name__}: {e}"
    try:
        report["bank_lines_registered"] = register_bank_lines(ws_id, ws_dir / "docs" / "bank", currency=currency)
    except Exception as e:  # noqa: BLE001
        report["bank_lines_registered"] = f"skipped: {type(e).__name__}: {e}"
    try:
        report["pf"] = seed_pf(ws_id, period, currency)
    except Exception as e:  # noqa: BLE001
        report["pf"] = f"skipped: {type(e).__name__}: {e}"
    try:
        from ..taxus.demo_us import (
            build_demo_us,  # US/Texas sole-prop workspace for the US tax + cross-border endpoints
        )

        report["demo_us"] = build_demo_us(None)
    except Exception as e:  # noqa: BLE001
        report["demo_us"] = f"skipped: {type(e).__name__}: {e}"
    try:
        from ..business.demo_biz import (
            build_demo_biz,  # MX persona moral workspace for the business endpoints
        )

        report["demo_biz"] = build_demo_biz(None)
    except Exception as e:  # noqa: BLE001
        report["demo_biz"] = f"skipped: {type(e).__name__}: {e}"
    marker = ws_dir / "docs" / "demo-extras.json"
    marker.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report
