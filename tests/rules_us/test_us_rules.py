"""Unit tests for the us.* and xb.* rules, beyond what the YAML vectors cover."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.rules.registry import Rule, load_rules, registry
from aurum.rules.us import constants_2026 as K
from aurum.rules.us.federal import bracket_tax, normalize_status, quarterly_estimate, self_employment_tax
from aurum.rules.us.texas import franchise, sales_use

US_RULE_IDS = {
    "us.fed.schedule_c_net",
    "us.fed.se_tax",
    "us.fed.income_tax",
    "us.fed.quarterly_estimate",
    "us.tx.franchise_no_tax_due",
    "us.tx.sales_use_basics",
    "xb.residency",
    "xb.treaty_tiebreaker",
    "xb.fbar",
    "xb.feie_vs_ftc",
}


def test_every_us_and_xb_rule_is_registered_and_satisfies_the_protocol():
    load_rules()
    by_id = {r.id: r for r in registry.list()}
    assert US_RULE_IDS <= set(by_id)
    for rule_id in US_RULE_IDS:
        rule = by_id[rule_id]
        assert isinstance(rule, Rule)
        assert rule.citation.law and rule.citation.article
        assert rule.effective_from <= date(2026, 1, 1)
        assert rule.version == "2026.1"


def test_every_result_carries_a_citation_and_the_not_advice_line():
    load_rules()
    samples = {
        "us.fed.schedule_c_net": {"gross_receipts": "1000"},
        "us.fed.se_tax": {"net_profit": "1000"},
        "us.fed.income_tax": {"taxable_income": "1000"},
        "us.fed.quarterly_estimate": {"current_year_tax": "8000"},
        "us.tx.franchise_no_tax_due": {"total_revenue": "1000"},
        "us.tx.sales_use_basics": {"taxable_sales": "1000"},
        "xb.residency": {"days_us": 10},
        "xb.treaty_tiebreaker": {"dual_resident": True},
        "xb.fbar": {"foreign_accounts": []},
        "xb.feie_vs_ftc": {"foreign_earned_income": "1000"},
    }
    for rule_id, inputs in samples.items():
        result = registry.get(rule_id).compute(lang="en", **inputs)
        assert result.explain.citations, rule_id
        assert result.explain.rule_versions == [f"{rule_id}@2026.1"], rule_id
        assert result.explain.steps, rule_id
        assert "Informational only" in result.explain.summary, rule_id


def test_constants_carry_a_source_and_the_verified_ones_have_a_date():
    for const in K.ALL:
        assert const.source_url.startswith("http"), const.key
        assert const.citation.law
        if const.verified:
            assert const.verified_on is not None, const.key
            assert const.mark == ""
        else:
            assert const.mark == " (verify)", const.key


def test_the_2026_bracket_tables_match_the_revenue_procedure_top_bracket_amounts():
    # Rev. Proc. 2025-32 § 4.01 states the tax at the start of the 37% bracket for each table.
    expected = {
        "mfj": (Decimal("768700"), Decimal("206583.50")),
        "hoh": (Decimal("640600"), Decimal("191171")),
        "single": (Decimal("640600"), Decimal("192979.25")),
        "mfs": (Decimal("384350"), Decimal("103291.75")),
    }
    for status, (threshold, tax_at_threshold) in expected.items():
        assert bracket_tax(threshold, status).tax == tax_at_threshold, status


def test_se_tax_caps_the_oasdi_portion_at_the_wage_base():
    se = self_employment_tax(Decimal("1000000"), "single")
    assert se.oasdi_base == K.SS_WAGE_BASE.value
    assert se.oasdi == (K.SS_WAGE_BASE.value * K.SE_OASDI_RATE.value).quantize(Decimal("0.01"))
    assert se.deductible_half == ((se.oasdi + se.medicare) / 2).quantize(Decimal("0.01"))
    # The additional Medicare tax is not half-deductible.
    assert se.total > se.oasdi + se.medicare


def test_quarterly_estimate_picks_the_smaller_leg():
    small_prior = quarterly_estimate(Decimal("40000"), "single", Decimal("10000"), Decimal("50000"))
    assert small_prior.required_annual == Decimal("10000.00")
    big_prior = quarterly_estimate(Decimal("40000"), "single", Decimal("90000"), Decimal("50000"))
    assert big_prior.required_annual == Decimal("36000.00")
    assert big_prior.due_dates[0] == date(2026, 4, 15)
    assert big_prior.due_dates[-1] == date(2027, 1, 15)


def test_franchise_sole_proprietor_is_never_a_taxable_entity():
    result = franchise(Decimal("50000000"), entity_type="sole_proprietorship")
    assert result.taxable_entity is False
    assert result.tax == Decimal("0.00")
    assert result.no_tax_due is True


def test_franchise_picks_the_lowest_of_the_four_margin_options():
    result = franchise(Decimal("10000000"), entity_type="llc", compensation=Decimal("9000000"), lang="en")
    assert result.margin_method == "total revenue − compensation"
    assert result.margin == Decimal("1000000.00")


def test_sales_use_caps_the_local_rate_at_two_percent():
    result = sales_use(Decimal("1000"), local_rate=Decimal("0.09"))
    assert result.capped is True
    assert result.combined_rate == K.TX_SALES_MAX_COMBINED_RATE.value


def test_unknown_filing_status_is_rejected():
    with pytest.raises(ValueError):
        normalize_status("widower")


def test_float_money_inputs_are_refused():
    load_rules()
    with pytest.raises(TypeError):
        registry.get("us.fed.se_tax").compute(net_profit=1000.5)


def test_rules_endpoint_lists_the_new_rules_with_citations():
    client = TestClient(create_app())
    rows = client.get("/api/rules/").json()
    ids = {r["id"] for r in rows}
    assert US_RULE_IDS <= ids
    for row in rows:
        if row["id"] in US_RULE_IDS:
            assert row["citation"]["law"]
            assert row["citation"]["url"]


def test_compute_endpoint_runs_a_us_rule():
    client = TestClient(create_app())
    response = client.post(
        "/api/rules/us.fed.income_tax/compute",
        json={"filing_status": "single", "taxable_income": "100000"},
    )
    assert response.status_code == 200
    assert response.json()["value"] == {"amount": "16712.00", "currency": "USD"}
