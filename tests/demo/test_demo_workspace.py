"""The demo workspace is the fixture every end-to-end check runs on."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from lxml import etree

from aurum.core.config import settings
from aurum.core.workspaces import get_workspace
from aurum.demo.generate import WS_ID, build_demo
from aurum.ledger.beancount_store import BeancountLedger
from aurum.tax.month_close import month_close


@pytest.fixture
def demo() -> dict:
    return build_demo()


def test_workspace_profile(demo):
    ws = get_workspace(WS_ID)
    assert ws.kind == "personal"
    assert ws.jurisdictions == ["MX"]
    assert ws.profile["rfc"] == "XAXX010101000"
    assert ws.profile["regime"] == "RESICO_PF"
    assert ws.profile["state"] == "NL"


def test_cfdi_xml_files_are_written_and_parse(demo):
    cfdi_dir = settings().workspace_dir(WS_ID) / "docs" / "cfdi"
    xmls = sorted(cfdi_dir.glob("*.xml"))
    assert len(xmls) == demo["documents"] == 12
    root = etree.parse(str(cfdi_dir / "AGO-PUE-D.xml")).getroot()
    assert root.get("Version") == "4.0"
    assert root.get("MetodoPago") == "PUE"
    ns = {"tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"}
    assert root.find(".//tfd:TimbreFiscalDigital", ns).get("UUID") == "AGO-PUE-D"


def test_rep_complement_carries_the_payment(demo):
    path = settings().workspace_dir(WS_ID) / "docs" / "cfdi" / "REP-JUL-1.xml"
    root = etree.parse(str(path)).getroot()
    ns = {"pago20": "http://www.sat.gob.mx/Pagos20"}
    pago = root.find(".//pago20:Pago", ns)
    assert pago.get("FechaPago").startswith("2026-07-08")
    assert pago.get("Monto") == "34800.00"
    assert root.find(".//pago20:DoctoRelacionado", ns).get("IdDocumento") == "JUN-PPD-B"


def test_no_real_rfcs_are_shipped(demo):
    """Fixtures are synthetic: only the SAT generic RFC and invented DEMO patterns."""
    index = json.loads((settings().workspace_dir(WS_ID) / "docs" / "cfdi" / "index.json").read_text("utf-8"))
    rfcs = {d["emisor_rfc"] for d in index["documents"]} | {d["receptor_rfc"] for d in index["documents"]}
    assert rfcs <= {"XAXX010101000", "DPM010101AA1", "DPF010101BB2", "DPR010101CC3"}


def test_bank_csv_exists_and_omits_the_uncollected_invoice(demo):
    csv_path = settings().workspace_dir(WS_ID) / "docs" / "bank" / "bbva-2026-08.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert "AGO-PUE-D" in text
    assert "AGO-PUE-E" not in text  # invoiced, never collected
    assert "DEPOSITO EN EFECTIVO VENTANILLA" in text  # deposit with no CFDI


def test_ledger_loads_without_errors_and_is_balanced(demo):
    ledger = BeancountLedger()
    entries, errors = ledger.load(WS_ID)
    assert errors == []
    assert len(ledger.journal(WS_ID)) == demo["transactions_posted"]
    balances = ledger.balances(WS_ID)
    assert balances["Assets:Bank:BBVA"][0].amount == Decimal("123217.50")
    assert balances["Assets:Taxes:ISR-Retenido"][0].amount == Decimal("562.50")
    assert balances["Equity:Opening"][0].amount == Decimal("-55000.00")


def test_manifest_diffs_are_exactly_what_the_audit_finds(demo):
    payload = month_close(WS_ID, demo["audit_period"], rfc=demo["rfc"])
    found = {d["kind"]: d for d in payload["diffs"]}
    assert set(found) == {d["kind"] for d in demo["expected_diffs"]}
    for expected in demo["expected_diffs"]:
        got = found[expected["kind"]]
        assert got["amount"]["amount"] == expected["amount"], expected["kind"]
        assert got["documents"] == expected["documents"], expected["kind"]


@pytest.mark.parametrize("period", ["2026-06", "2026-07", "2026-08"])
def test_manifest_figures_match(demo, period):
    payload = month_close(WS_ID, period, rfc=demo["rfc"])
    expected = demo["expected_figures"][period]
    assert payload["income"]["collected"]["amount"] == expected["income_collected"]
    assert payload["isr"]["value"]["amount"] == expected["isr"]
    assert payload["iva"]["payable"]["amount"] == expected["iva_payable"]
    if "isr_retenido" in expected:
        assert payload["retentions"]["isr"]["amount"] == expected["isr_retenido"]


def test_build_demo_is_idempotent(demo):
    ledger = BeancountLedger()
    before = len(ledger.journal(WS_ID))
    again = build_demo()
    assert again == demo
    assert len(ledger.journal(WS_ID)) == before


def test_build_demo_accepts_an_explicit_data_dir(tmp_path):
    data = build_demo(tmp_path / "other")
    assert (tmp_path / "other" / "workspaces" / WS_ID / "main.beancount").exists()
    assert data["workspace"] == WS_ID


# --- demo/extras.register_pf_accounts ----------------------------------------------------------------


def test_register_pf_accounts_adds_three_rows_without_touching_the_ledger(demo):
    from aurum.demo.extras import register_pf_accounts
    from aurum.pf import store

    ledger = BeancountLedger()
    before_len = len(ledger.journal(WS_ID))
    before_balance = ledger.balances(WS_ID)["Assets:Bank:BBVA"][0].amount

    result = register_pf_accounts(WS_ID)
    assert result["accounts_created"] == 3

    conn = store.db()
    rows = {
        r["name"]: r["account"]
        for r in conn.execute("SELECT name, account FROM pf_accounts WHERE ws_id=?", (WS_ID,)).fetchall()
    }
    assert rows == {
        "BBVA": "Assets:Bank:BBVA", "Efectivo": "Assets:Cash", "Tarjeta BBVA": "Liabilities:CreditCard:BBVA",
    }

    ledger2 = BeancountLedger()
    assert len(ledger2.journal(WS_ID)) == before_len
    assert ledger2.balances(WS_ID)["Assets:Bank:BBVA"][0].amount == before_balance


def test_register_pf_accounts_repoints_goals_and_is_idempotent(demo):
    from aurum.demo.extras import register_pf_accounts
    from aurum.pf import goals as pf_goals

    register_pf_accounts(WS_ID)
    by_name = {g["name"]: g["account"] for g in pf_goals.list_goals(WS_ID)}
    assert by_name["Fondo de emergencia"] == "Assets:Bank:BBVA"
    assert by_name["Laptop nueva"] == "Assets:Cash"

    second = register_pf_accounts(WS_ID)
    assert second["accounts_created"] == 0  # INSERT OR IGNORE: no duplicate rows
    from aurum.pf import store

    conn = store.db()
    (count,) = conn.execute("SELECT COUNT(*) FROM pf_accounts WHERE ws_id=?", (WS_ID,)).fetchone()
    assert count == 3
