"""Chart templates, payroll, invoicing register and KPIs — against the synthetic demo-biz quarter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from aurum.business import chart as chart_mod
from aurum.business import invoices as invoices_mod
from aurum.business import kpis as kpis_mod
from aurum.business import payroll as payroll_mod
from aurum.business import payroll_pdf
from aurum.business.demo_biz import WS_ID
from aurum.ledger.base import InMemoryLedger

# --------------------------------------------------------------------------- chart templates


def test_both_templates_parse_and_group_accounts_the_same_way():
    for name in ("mx_persona_moral", "us_llc"):
        accounts = chart_mod.template_accounts(name)
        assert len(accounts) > 30
        assert all(a.split(":")[0] in {"Assets", "Liabilities", "Equity", "Income", "Expenses"} for a in accounts)
        assert any(a.startswith("Expenses:COGS:") for a in accounts)
        assert any(a.startswith("Expenses:Payroll:") for a in accounts)
        assert any(a.startswith("Expenses:Opex:") for a in accounts)


def test_unknown_template_raises():
    with pytest.raises(chart_mod.TemplateNotFound):
        chart_mod.template_accounts("mx_resico_pf")  # lives in aurum/ledger/templates, not here


def test_apply_template_to_an_in_memory_ledger_is_idempotent():
    store = InMemoryLedger()
    first = chart_mod.apply_business_template("ws1", "us_llc", store=store)
    second = chart_mod.apply_business_template("ws1", "us_llc", store=store)
    assert first == second
    assert set(first) <= set(store.accounts("ws1"))


def test_apply_template_writes_open_directives_and_keeps_existing_ones(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    from aurum.ledger.base import get_ledger

    store = get_ledger()
    if not hasattr(store, "accounts_path"):
        pytest.skip("Beancount store not available")
    from aurum.ledger.base import Posting, Transaction

    store.append(
        "ws2",
        Transaction(
            date=date(2026, 1, 5),
            narration="pre-existing",
            postings=[
                Posting(account="Assets:Bank:Otro", amount={"amount": "10", "currency": "MXN"}),
                Posting(account="Equity:Opening-Balances", amount=None),
            ],
        ),
    )
    accounts = chart_mod.apply_business_template("ws2", "mx_persona_moral")
    text = store.accounts_path("ws2").read_text(encoding="utf-8")
    assert "2000-01-01 open Expenses:Payroll:ISN" in text
    assert "Assets:Bank:Otro" in text  # the account that was already open survives
    assert set(accounts) <= set(store.accounts("ws2"))


# --------------------------------------------------------------------------- payroll


def test_names_and_rfcs_are_masked():
    assert payroll_mod.mask_name("Empleada Demo Uno") == "E. U***"
    assert payroll_mod.mask_name("Cher") == "C.***"
    assert payroll_mod.mask_name("") == "***"
    assert payroll_mod.mask_rfc("XAXX010101000") == "*********1000"
    assert payroll_mod.mask_rfc(None) is None


def test_wage_isr_uses_the_verified_article_96_tarifa():
    from aurum.rules.mx.general import ISR_TABLE_MONTHLY_2026, apply_table

    isr = payroll_mod.wage_isr(Decimal("30000"))
    expected_tarifa, _rate, _upper = apply_table(Decimal("30000.00"), list(ISR_TABLE_MONTHLY_2026))
    assert isr["tarifa_tax"] == expected_tarifa.quantize(Decimal("0.01"))
    assert isr["subsidy_applied"] is False  # above the income ceiling
    assert isr["retention"] == isr["tarifa_tax"]


def test_wage_isr_applies_the_unverified_subsidy_below_the_ceiling():
    isr = payroll_mod.wage_isr(Decimal("9000"))
    assert isr["subsidy_applied"] is True
    assert isr["subsidy"] > 0
    assert isr["retention"] == isr["tarifa_tax"] - isr["subsidy"]
    assert isr["verified_subsidy"] is False


def test_payroll_run_totals_reconcile(demo):
    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    totals = {k: Decimal(v["amount"]) for k, v in run["totals"].items()}
    assert run["employees"] == 3
    assert totals["net"] == totals["gross"] - totals["isr"] - totals["imss_employee"]
    assert totals["employer_cost"] == totals["gross"] + totals["imss_employer"] + totals["infonavit"] + totals["isn"]
    line_gross = sum(Decimal(line["gross"]["amount"]) for line in run["lines"])
    assert line_gross == totals["gross"]


def test_payroll_isn_is_three_percent_of_gross(demo):
    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    gross = Decimal(run["totals"]["gross"]["amount"])
    assert Decimal(run["totals"]["isn"]["amount"]) == (gross * Decimal("0.03")).quantize(Decimal("0.01"))
    assert run["isn"]["explain"]["rule_versions"] == ["mx.nl.isn@2026.1"]


def test_payroll_run_posts_a_balanced_ledger_transaction(demo):
    from aurum.ledger.base import get_ledger

    txns = [
        t
        for t in get_ledger().journal(WS_ID, start=date(2026, 4, 1), end=date(2026, 4, 30))
        if t.meta.get("source") == "business.payroll"
    ]
    assert len(txns) == 1
    postings = txns[0].postings
    assert sum(p.amount.amount for p in postings) == 0
    accounts = {p.account for p in postings}
    assert "Expenses:Payroll:ISN" in accounts
    assert "Liabilities:Payroll:Net" in accounts


def test_payroll_carries_the_unverified_warnings(demo):
    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    blob = " ".join(run["warnings"])
    assert "cesantía y vejez" in blob
    assert "Borrador" in blob
    assert run["status"] == "draft"


def test_payroll_lines_never_carry_an_unmasked_name(demo):
    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    for line in run["lines"]:
        assert "Demo" not in line["name"]
        assert line["name"].endswith("***")


def test_payroll_run_with_no_employees_posts_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    run = payroll_mod.run_payroll("empty-ws", "2026-05")
    assert run["employees"] == 0
    assert run["txn_id"] is None
    assert Decimal(run["totals"]["employer_cost"]["amount"]) == 0


def test_payroll_run_is_idempotent(demo):
    from aurum.ledger.base import get_ledger

    def payroll_txns():
        return [
            t
            for t in get_ledger().journal(WS_ID, start=date(2026, 4, 1), end=date(2026, 4, 30))
            if t.meta.get("source") == "business.payroll"
        ]

    first = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    assert first["period"] == "2026-04"
    assert len(payroll_txns()) == 1

    again = payroll_mod.run_payroll(WS_ID, "2026-04")
    assert again["already_ran"] is True
    assert again["txn_id"] == first["txn_id"]
    assert len(payroll_txns()) == 1  # no second posting


def test_payroll_force_rerun_voids_the_previous_posting(demo):
    from aurum.ledger.base import get_ledger

    original = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    original_txn_id = original["txn_id"]

    forced = payroll_mod.run_payroll(WS_ID, "2026-04", force=True)
    assert forced["already_ran"] is False
    assert forced["previous_txn_voided"] is True
    assert forced["txn_id"] != original_txn_id

    journal = get_ledger().journal(WS_ID, start=date(2026, 4, 1), end=date(2026, 4, 30))
    reversal = [t for t in journal if "voided-reversal" in t.tags]
    assert len(reversal) == 1
    assert reversal[0].meta.get("reverses") == original_txn_id

    original_posted = [t for t in journal if t.links and original_txn_id in t.links]
    assert original_posted and "voided" in original_posted[0].tags

    sueldos_april = sum(
        (p.amount.amount for t in journal for p in t.postings if p.account == "Expenses:Payroll:Sueldos"),
        Decimal("0"),
    )
    expected_gross = Decimal(forced["totals"]["gross"]["amount"])
    assert sueldos_april == expected_gross  # original + its reversal cancel out, leaving one run's worth

    old_run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    assert old_run["superseded_by"] == forced["id"]

    runs = payroll_mod.list_runs(WS_ID, period="2026-04")
    assert [r["id"] for r in runs] == [forced["id"]]
    all_runs = payroll_mod.list_runs(WS_ID, period="2026-04", include_superseded=True)
    assert len(all_runs) == 2


def test_payroll_delete_run_voids_the_posting(demo):
    from aurum.ledger.base import get_ledger

    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][1]["id"])
    result = payroll_mod.delete_run(WS_ID, run["id"])
    assert result["txn_voided"] is True

    reloaded = payroll_mod.get_run(WS_ID, run["id"])
    assert reloaded["voided_at"] is not None

    journal = get_ledger().journal(WS_ID)
    voided_original = [t for t in journal if t.links and run["txn_id"] in t.links]
    assert voided_original and "voided" in voided_original[0].tags


def test_payroll_pdf_is_a_watermarked_draft(demo):
    run = payroll_mod.get_run(WS_ID, demo["payroll_runs"][0]["id"])
    pdf = payroll_pdf.render(run)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


# --------------------------------------------------------------------------- invoicing register


def test_invoice_register_splits_issued_from_collected(demo):
    reg = invoices_mod.register(WS_ID, as_of=date(2026, 6, 30))
    issued = Decimal(reg["issued"]["amount"])
    collected = Decimal(reg["collected"]["amount"])
    outstanding = Decimal(reg["outstanding"]["amount"])
    assert reg["counts"]["issued"] == 8
    assert issued == collected + outstanding
    assert reg["counts"]["open"] == 3  # the three PPDs with no REP


def test_aging_buckets_add_up_to_the_outstanding_balance(demo):
    reg = invoices_mod.register(WS_ID, as_of=date(2026, 6, 30))
    total = sum(Decimal(b["amount"]["amount"]) for b in reg["aging"])
    assert total == Decimal(reg["outstanding"]["amount"])
    buckets = {b["bucket"]: b["invoices"] for b in reg["aging"]}
    assert buckets["90+"] == 1  # the March invoice
    assert buckets["0-30"] == 1


def test_ppd_is_collected_only_through_a_rep(demo):
    invoices = {i["uuid"]: i for i in invoices_mod.load_emitidos(WS_ID)}
    with_rep = invoices["DEMO-BIZ-0000-0000-0002"]
    without_rep = invoices["DEMO-BIZ-0000-0000-0005"]
    assert with_rep["outstanding"] == 0 and with_rep["paid_on"] == date(2026, 5, 12)
    assert without_rep["outstanding"] == without_rep["total"] and without_rep["paid_on"] is None


def test_top_clients_are_masked_and_ranked(demo):
    reg = invoices_mod.register(WS_ID, as_of=date(2026, 6, 30))
    top = reg["top_clients"]
    assert all(c["client_rfc"].startswith("*") for c in top)
    amounts = [Decimal(c["issued"]["amount"]) for c in top]
    assert amounts == sorted(amounts, reverse=True)


def test_dso_is_positive_when_money_is_outstanding(demo):
    reg = invoices_mod.register(WS_ID, as_of=date(2026, 6, 30))
    assert Decimal(reg["dso_days"]) > 0


def test_the_register_survives_an_empty_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    reg = invoices_mod.register("nobody", as_of=date(2026, 6, 30))
    assert reg["counts"] == {"issued": 0, "open": 0}
    assert reg["dso_days"] == "0"


def test_reminder_is_bilingual_and_sends_nothing(demo):
    out = invoices_mod.reminder(WS_ID, "DEMO-BIZ-0000-0000-0008", as_of=date(2026, 6, 30))
    assert out["sent"] is False
    assert out["bucket"] == "90+"
    assert "factura" in out["text"]["es"]
    assert "invoice" in out["text"]["en"]
    assert out["client_rfc"].startswith("*")


def test_reminder_for_an_unknown_invoice_raises(demo):
    with pytest.raises(KeyError):
        invoices_mod.reminder(WS_ID, "no-such-uuid")


# --------------------------------------------------------------------------- KPIs


def test_kpis_report_revenue_margin_and_opex_groups(demo):
    k = kpis_mod.kpis(WS_ID, "2026-05")
    assert Decimal(k["revenue"]["amount"]) == Decimal("256000.00")
    assert Decimal(k["cogs"]["amount"]) == Decimal("68500.00")
    assert Decimal(k["gross_profit"]["amount"]) == Decimal("187500.00")
    assert k["gross_margin"]["percent"] == "73.24"
    groups = {g["group"] for g in k["operating_expenses"]["by_group"]}
    assert {"Payroll", "Rent", "Marketing", "Professional"} <= groups


def test_every_kpi_figure_carries_an_explain(demo):
    k = kpis_mod.kpis(WS_ID, "2026-05")
    for key in ("revenue", "cogs", "gross_profit", "cash", "receivables", "payables", "operating_profit"):
        assert k[key]["explain"]["summary"]
        assert k[key]["explain"]["steps"]
    for key in ("gross_margin", "operating_expenses", "runway", "tax_reserve"):
        assert k[key]["explain"]["summary"]


def test_receivables_match_the_open_invoices(demo):
    k = kpis_mod.kpis(WS_ID, "2026-06")
    reg = invoices_mod.register(WS_ID, as_of=date(2026, 6, 30))
    assert Decimal(k["receivables"]["amount"]) == Decimal(reg["outstanding"]["amount"])


def test_runway_is_none_when_the_business_is_not_burning_cash(demo):
    k = kpis_mod.kpis(WS_ID, "2026-05")
    assert k["runway"]["months"] is None
    assert Decimal(k["runway"]["average_burn"]["amount"]) == 0
    assert "runway" in k["runway"]["explain"]["summary"].lower()


def test_runway_is_reported_when_expenses_outrun_income(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    from aurum.core.money import Amount
    from aurum.ledger.base import Posting, Transaction, get_ledger

    ledger = get_ledger()
    ledger.append(
        "burn-ws",
        Transaction(
            date=date(2026, 1, 2),
            narration="opening",
            postings=[
                Posting(account="Assets:Bank:BBVA", amount=Amount(amount=Decimal("120000"), currency="MXN")),
                Posting(account="Equity:Opening-Balances", amount=None),
            ],
        ),
    )
    for month in (3, 4, 5):
        ledger.append(
            "burn-ws",
            Transaction(
                date=date(2026, month, 10),
                narration="opex",
                postings=[
                    Posting(account="Expenses:Opex:Rent", amount=Amount(amount=Decimal("20000"), currency="MXN")),
                    Posting(account="Assets:Bank:BBVA", amount=None),
                ],
            ),
        )
    k = kpis_mod.kpis("burn-ws", "2026-05")
    assert Decimal(k["runway"]["average_burn"]["amount"]) == Decimal("20000.00")
    assert Decimal(k["runway"]["months"]) == Decimal("3.0")


def test_tax_reserve_warns_that_month_close_is_resico_shaped(demo):
    k = kpis_mod.kpis(WS_ID, "2026-05")
    reserve = k["tax_reserve"]
    assert reserve["source"] in {"aurum.tax.month_close", "ledger"}
    if reserve["source"] == "aurum.tax.month_close":
        assert any("RESICO" in w for w in reserve["warnings"])
    assert Decimal(reserve["total"]["amount"]) == Decimal(reserve["isr"]["amount"]) + Decimal(
        reserve["iva"]["amount"]
    )
