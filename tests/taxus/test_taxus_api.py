"""End-to-end tests for /api/tax/us against the demo-us workspace in a temporary data dir."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.money import Amount
from aurum.core.workspaces import Workspace, save_workspace
from aurum.ledger.base import Posting, Transaction, get_ledger
from aurum.taxus import inputs as ledger_inputs
from aurum.taxus.demo_us import build_demo_us


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo_us(tmp_path / "data")
    return TestClient(create_app())


def test_annual_payload_matches_the_demo_manifest(client):
    payload = client.get("/api/tax/us/demo-us/2026").json()
    assert payload["applicable"] is True
    assert payload["currency"] == "USD"
    sched = payload["schedule_c"]
    assert sched["gross_receipts"]["amount"] == "141000.00"
    assert sched["returns_and_allowances"]["amount"] == "1500.00"
    assert sched["cost_of_goods_sold"]["amount"] == "12000.00"
    assert sched["expenses"]["amount"] == "9810.00"
    assert sched["net"]["amount"] == "117690.00"
    assert sched["transactions"] == 27
    # 141000 - 1500 - 12000 - 9810
    assert Decimal(sched["net"]["amount"]) == Decimal("141000.00") - Decimal("1500.00") - Decimal(
        "12000.00"
    ) - Decimal("9810.00")


def test_every_section_carries_an_explain_with_rule_versions(client):
    payload = client.get("/api/tax/us/demo-us/2026").json()
    for section in ("schedule_c", "se_tax", "income_tax", "quarterly"):
        explain = payload[section]["explain"]
        assert explain["summary"]
        assert explain["steps"]
        assert explain["citations"]
        assert explain["rule_versions"]
    assert payload["quarterly"]["due_dates"] == ["2026-04-15", "2026-06-15", "2026-09-15", "2027-01-15"]
    assert payload["disclaimer"].startswith("This is an organizer, not a tax return")
    assert payload["status"] == "draft"


def test_total_tax_is_income_tax_plus_se_tax(client):
    payload = client.get("/api/tax/us/demo-us/2026").json()
    total = Decimal(payload["income_tax"]["value"]["amount"]) + Decimal(payload["se_tax"]["value"]["amount"])
    assert Decimal(payload["total_tax"]["amount"]) == total
    assert Decimal(payload["quarterly"]["amount_each"]["amount"]) > 0


def test_mx_only_workspace_gets_a_clear_not_applicable_200(client):
    save_workspace(Workspace(id="mx-only", name="MX only", jurisdictions=["MX"]))
    response = client.get("/api/tax/us/mx-only/2026")
    assert response.status_code == 200
    payload = response.json()
    assert payload["applicable"] is False
    assert "no US profile" in payload["reason"]
    assert payload["warnings"]


def test_unknown_workspace_is_also_a_not_applicable_200(client):
    payload = client.get("/api/tax/us/nope/2026").json()
    assert payload["applicable"] is False


def test_an_out_of_range_year_is_rejected(client):
    assert client.get("/api/tax/us/demo-us/1900").status_code == 400


def test_organizer_pdf_is_a_draft_pdf(client):
    response = client.get("/api/tax/us/demo-us/2026/organizer.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "DRAFT" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 2000


def test_organizer_pdf_renders_even_when_not_applicable(client):
    save_workspace(Workspace(id="mx-only2", name="MX only", jurisdictions=["MX"]))
    response = client.get("/api/tax/us/mx-only2/2026/organizer.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_tx_franchise_says_no_tax_due_for_a_sole_proprietor(client):
    payload = client.get("/api/tax/us/demo-us/2026/tx-franchise").json()
    assert payload["no_tax_due"] is True
    assert payload["tax"]["amount"] == "0.00"
    assert payload["no_tax_due_threshold"]["amount"] == "2650000.00"
    assert "171.0002" in payload["explain"]["summary"]


def test_constants_endpoint_reports_verification_status(client):
    payload = client.get("/api/tax/us/constants").json()
    assert payload["year"] == 2026
    assert payload["verified"] > 20
    keys = {row["key"] for row in payload["constants"]}
    assert "fed.standard_deduction" in keys
    assert "tx.franchise.no_tax_due_threshold" in keys
    for row in payload["constants"]:
        assert row["source_url"].startswith("http")


def test_mixed_workspace_only_counts_us_marked_postings(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    ws = save_workspace(
        Workspace(id="mixed", name="Mixed", jurisdictions=["MX", "US"], base_currency="USD")
    )
    ledger = get_ledger()
    ledger.append(
        "mixed",
        Transaction(
            date=date(2026, 3, 1),
            narration="US consulting, marked by account segment",
            postings=[
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("1000"), currency="USD")),
                Posting(account="Income:US:Consulting", amount=Amount(amount=Decimal("-1000"), currency="USD")),
            ],
        ),
    )
    ledger.append(
        "mixed",
        Transaction(
            date=date(2026, 4, 1),
            narration="US consulting, marked by tag",
            postings=[
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("500"), currency="USD")),
                Posting(account="Income:Consulting", amount=Amount(amount=Decimal("-500"), currency="USD")),
            ],
            tags=["us"],
        ),
    )
    ledger.append(
        "mixed",
        Transaction(
            date=date(2026, 5, 1),
            narration="Mexican income, not marked",
            postings=[
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("9999"), currency="USD")),
                Posting(account="Income:MX:Consulting", amount=Amount(amount=Decimal("-9999"), currency="USD")),
            ],
        ),
    )
    collected = ledger_inputs.collect(ledger, ws, 2026)
    assert collected.gross_receipts == Decimal("1500.00")
    assert collected.transactions == 2


def test_cogs_accounts_are_split_out_of_expenses(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    ws = save_workspace(Workspace(id="us-only", name="US", jurisdictions=["US"], base_currency="USD"))
    ledger = get_ledger()
    ledger.append(
        "us-only",
        Transaction(
            date=date(2026, 2, 1),
            narration="Materials",
            postings=[
                Posting(account="Expenses:COGS:Materials", amount=Amount(amount=Decimal("300"), currency="USD")),
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("-300"), currency="USD")),
            ],
        ),
    )
    ledger.append(
        "us-only",
        Transaction(
            date=date(2026, 2, 2),
            narration="Software",
            postings=[
                Posting(account="Expenses:Software", amount=Amount(amount=Decimal("100"), currency="USD")),
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("-100"), currency="USD")),
            ],
        ),
    )
    collected = ledger_inputs.collect(ledger, ws, 2026)
    assert collected.cost_of_goods_sold == Decimal("300.00")
    assert collected.expenses_total == Decimal("100.00")


def test_non_usd_postings_are_skipped_with_a_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    ws = save_workspace(Workspace(id="us-mxn", name="US", jurisdictions=["US"], base_currency="USD"))
    get_ledger().append(
        "us-mxn",
        Transaction(
            date=date(2026, 2, 1),
            narration="Peso invoice",
            postings=[
                Posting(account="Assets:Bank", amount=Amount(amount=Decimal("1000"), currency="MXN")),
                Posting(account="Income:Consulting", amount=Amount(amount=Decimal("-1000"), currency="MXN")),
            ],
        ),
    )
    collected = ledger_inputs.collect(get_ledger(), ws, 2026)
    assert collected.gross_receipts == Decimal("0.00")
    assert any("MXN" in w for w in collected.warnings)


def test_build_demo_us_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    first = build_demo_us(tmp_path / "data")
    second = build_demo_us(tmp_path / "data")
    assert first == second
    assert first["transactions_posted"] == 27
