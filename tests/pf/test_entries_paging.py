"""The entries envelope — keyset pages, totals over the full filtered set, foreign rows included."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction
from aurum.pf import accounts_admin, entries


def _acct(ws="ws", name="Efectivo", type_="cash"):
    return accounts_admin.create_account(ws, accounts_admin.AccountIn(name=name, type=type_))


def _bulk(client, acct, n, amount="10", start_day=1):
    bodies = [
        {"kind": "expense", "date": f"2026-09-{(start_day + i) % 28 + 1:02d}",
         "amount": {"amount": amount, "currency": "MXN"}, "account_id": acct["id"], "payee": f"p{i}"}
        for i in range(n)
    ]
    r = client.post("/api/pf/ws/entries/bulk", json={"entries": bodies})
    assert r.status_code == 200, r.text
    return r.json()["created"]


def test_pages_are_disjoint_and_totals_cover_everything(ledger, client):
    acct = _acct()
    ids = set(_bulk(client, acct, 120))
    r = client.get("/api/pf/ws/entries?limit=50")
    assert r.status_code == 200
    page = r.json()
    assert len(page["entries"]) == 50 and page["next_cursor"]
    assert page["totals"]["count"] == 120
    assert page["totals"]["out"] == {"amount": "1200.00", "currency": "MXN"}
    assert page["totals"]["in"]["amount"] == "0.00" and page["totals"]["net"]["amount"] == "-1200.00"
    assert all("editable" in e and "non_editable_reason" in e for e in page["entries"])

    seen = [e["id"] for e in page["entries"]]
    cursor = page["next_cursor"]
    while cursor:
        r = client.get(f"/api/pf/ws/entries?limit=50&cursor={cursor}")
        assert r.status_code == 200
        page = r.json()
        seen.extend(e["id"] for e in page["entries"])
        assert page["totals"]["count"] == 120  # totals never shrink with the page
        cursor = page["next_cursor"]
    assert len(seen) == 120 and set(seen) == ids
    # ordered (date desc, id desc)
    keys = [(e["date"], e["id"]) for e in entries.list_entries("ws", limit=500)["entries"]]
    assert keys == sorted(keys, reverse=True)


def test_default_limit_is_100_and_max_500(ledger, client):
    acct = _acct()
    _bulk(client, acct, 105)
    page = client.get("/api/pf/ws/entries").json()
    assert len(page["entries"]) == 100 and page["next_cursor"]
    assert client.get("/api/pf/ws/entries?limit=500").status_code == 200
    assert client.get("/api/pf/ws/entries?limit=501").status_code == 422


def test_totals_skip_transfers_and_foreign_currency_but_count_them(ledger, client):
    a = _acct()
    b = _acct(name="Banco", type_="checking")
    entries.create_entry("ws", entries.EntryIn(kind="income", date="2026-09-01", amount=Amount(amount="1000"), account_id=a["id"]))
    entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-09-02", amount=Amount(amount="300"), account_id=a["id"]))
    entries.create_entry("ws", entries.EntryIn(kind="transfer", date="2026-09-03", amount=Amount(amount="500"),
                                               account_id=a["id"], to_account_id=b["id"]))
    entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-09-04", amount=Amount(amount="20", currency="USD"),
                                               account_id=a["id"]))
    page = entries.list_entries("ws")
    assert page["totals"] == {
        "in": {"amount": "1000.00", "currency": "MXN"}, "out": {"amount": "300.00", "currency": "MXN"},
        "net": {"amount": "700.00", "currency": "MXN"}, "count": 4,
    }
    transfer = next(e for e in page["entries"] if e["kind"] == "transfer")
    assert transfer["amount"]["amount"] == "-500.00" and transfer["to_account_name"] == "Banco"
    assert entries.list_entries("ws", account_id=b["id"])["totals"]["count"] == 1


def test_foreign_rows_carry_the_asset_leg_and_resolved_account(ledger):
    a = _acct()
    ledger.append(
        "ws",
        Transaction(
            date=date(2026, 9, 10), payee="Nómina", narration="Pago de nómina",
            postings=[
                Posting(account=a["account"], amount=Amount(amount="8750")),
                Posting(account="Assets:Taxes:ISR-Retenido", amount=Amount(amount="1250")),
                Posting(account="Income:Salary"),
            ],
            tags=["payroll"],
        ),
    )
    page = entries.list_entries("ws")
    row = page["entries"][0]
    assert row["source"] == "payroll" and row["editable"] is False and row["non_editable_reason"]
    assert row["account_id"] == a["id"] and row["account_name"] == "Efectivo"
    assert row["amount"]["amount"] == "10000.00"  # Σ asset legs: the money that hit the accounts
    assert row["txn_id"] and row["commitment_id"] is None and row["voided"] is False
    assert page["totals"]["in"]["amount"] == "10000.00"


def test_cursor_is_opaque_and_bad_cursor_is_400(ledger, client):
    acct = _acct()
    _bulk(client, acct, 3)
    page = client.get("/api/pf/ws/entries?limit=1").json()
    cur = page["next_cursor"]
    assert "|" not in cur
    when, ident = entries.decode_cursor(cur)
    assert (when, ident) == (page["entries"][0]["date"], page["entries"][0]["id"])
    assert client.get("/api/pf/ws/entries?cursor=nope").status_code == 400


def test_filters_apply_to_totals_and_page(ledger, client):
    acct = _acct()
    entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-08-30", amount=Amount(amount="7"), account_id=acct["id"], payee="Tacos"))
    entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-09-01", amount=Amount(amount="9"), account_id=acct["id"], payee="Cafe"))
    r = client.get("/api/pf/ws/entries?from=2026-09-01&to=2026-09-30")
    assert r.json()["totals"]["count"] == 1 and r.json()["totals"]["out"]["amount"] == "9.00"
    r = client.get("/api/pf/ws/entries?q=taco")
    assert r.json()["totals"]["count"] == 1 and r.json()["entries"][0]["payee"] == "Tacos"
    assert Decimal(client.get("/api/pf/ws/entries?kind=income").json()["totals"]["count"]) == 0
