from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction
from aurum.pf import income


def test_income_by_month_gross_and_net(ledger):
    ledger.append(
        "ws",
        Transaction(
            date=date(2026, 8, 10),
            payee="Client A",
            narration="Honorarios con retencion ISR",
            postings=[
                Posting(account="Assets:Bank:Checking", amount=Amount(amount="8750")),
                Posting(account="Assets:Taxes:ISR-Retenido", amount=Amount(amount="1250")),
                Posting(account="Income:Freelance"),
            ],
        ),
    )
    out = income.get_income("ws", months=1, today=date(2026, 8, 15))
    month = out["months"][0]
    assert month["month"] == "2026-08"
    assert month["gross"]["amount"] == "10000.00"
    assert month["retained"]["amount"] == "1250.00"
    assert month["net"]["amount"] == "8750.00"


def test_iva_acreditable_is_never_counted_as_retained(ledger):
    ledger.append(
        "ws",
        Transaction(
            date=date(2026, 8, 12),
            payee="Proveedor",
            narration="Compra con IVA acreditable",
            postings=[
                Posting(account="Expenses:Work:Software", amount=Amount(amount="1000")),
                Posting(account="Assets:Taxes:IVA-Acreditable", amount=Amount(amount="160")),
                Posting(account="Assets:Bank:Checking"),
            ],
        ),
    )
    ledger.append(
        "ws",
        Transaction(
            date=date(2026, 8, 13), payee="Cliente", narration="Honorarios",
            postings=[
                Posting(account="Assets:Bank:Checking", amount=Amount(amount="9000")),
                Posting(account="Assets:Taxes:ISR-Retenido", amount=Amount(amount="1000")),
                Posting(account="Income:Freelance"),
            ],
        ),
    )
    out = income.get_income("ws", months=1, today=date(2026, 8, 15))
    assert out["months"][0]["retained"]["amount"] == "1000.00"


def test_income_router_defensive_without_cfdi_table(client):
    r = client.get("/api/pf/ws/income?months=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["months"]) == 3
    assert "smoothed_average" in body
