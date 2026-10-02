"""The three NL/IMSS/INFONAVIT rules beyond what the YAML vectors already assert."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aurum.rules.mx import nl_constants_2026 as K
from aurum.rules.mx.nl import capped_sbc, cv_employer_rate, employee_imss_quotas
from aurum.rules.registry import RuleNotFound, load_rules, registry


@pytest.fixture(autouse=True)
def _rules():
    load_rules()


def test_all_three_rules_are_registered_with_citations():
    for rule_id in ("mx.nl.isn", "mx.imss.employer_quotas", "mx.infonavit.employer"):
        rule = registry.get(rule_id)
        assert rule.version == "2026.1"
        assert rule.jurisdiction == "MX"
        assert rule.citation.url
        assert rule.citation.trust_tier == "primary"


def test_version_pinning_resolves_the_same_rule():
    assert registry.get("mx.nl.isn@2026.1").version == "2026.1"
    with pytest.raises(RuleNotFound):
        registry.get("mx.nl.isn@1999.1")


def test_isn_is_three_percent_of_the_taxable_base():
    result = registry.get("mx.nl.isn").compute(payroll="250000")
    assert result.value.amount == Decimal("7500.00")
    assert "3%" in result.explain.summary
    assert any("157" in c.article for c in result.explain.citations)


def test_isn_exemptions_come_from_article_160_only():
    rule = registry.get("mx.nl.isn")
    # aguinaldo is swept in by art. 154; fondo de ahorro is taken back out by art. 160 I g).
    taxed = rule.compute(concepts={"aguinaldo": "10000"})
    exempt = rule.compute(concepts={"fondo_ahorro": "10000"})
    assert taxed.value.amount == Decimal("300.00")
    assert exempt.value.amount == Decimal("0.00")


def test_the_sbc_ceiling_is_25_uma():
    sbc, ceiling, capped = capped_sbc(Decimal("99999"))
    assert ceiling == Decimal("2932.75") == (K.SBC_CAP_UMA.value * K.UMA_DAILY.value).quantize(Decimal("0.01"))
    assert sbc == ceiling and capped is True
    _sbc, _ceiling, uncapped = capped_sbc(Decimal("500"))
    assert uncapped is False


@pytest.mark.parametrize(
    ("sbc", "expected_rate"),
    [
        ("315.04", "0.03150"),  # exactly the minimum wage -> the 1.00 SM row
        ("150.00", "0.03150"),  # below the minimum wage (not legal) still lands in the first row
        ("330.00", "0.06026"),  # 2.51-3.00 UMA
        ("400.00", "0.06361"),  # 3.01-3.50 UMA
        ("450.00", "0.06613"),  # 3.51-4.00 UMA
        ("470.00", "0.07513"),  # 4.01 UMA en adelante
    ],
)
def test_cesantia_brackets(sbc, expected_rate):
    rate, _label = cv_employer_rate(Decimal(sbc))
    assert rate == Decimal(expected_rate)


def test_the_2026_cesantia_column_interpolates_the_verified_final_table():
    """The 2026 column is (verify); this is the cross-check recorded in the constants module."""
    final = {row["label"]: row["rate"] for row in K.CV_EMPLOYER_TABLE_FINAL.value}
    start = Decimal("0.03150")
    for row in K.CV_EMPLOYER_TABLE_2026.value:
        target = final[row["label"]]
        interpolated = start + (target - start) / 8 * 4
        assert abs(row["rate"] - interpolated) <= Decimal("0.00001"), row["label"]
    assert K.CV_EMPLOYER_TABLE_2026.verified is False
    assert K.CV_EMPLOYER_TABLE_FINAL.verified is True


def test_employer_quota_breakdown_covers_every_branch():
    breakdown = registry.get("mx.imss.employer_quotas").breakdown(sbc_daily="500", days="30")
    names = {row["branch"] for row in breakdown["branches"]}
    assert names == {
        "riesgos_trabajo",
        "em_especie_cuota_fija",
        "em_especie_excedente",
        "em_dinero",
        "gastos_medicos_pensionados",
        "invalidez_vida",
        "retiro",
        "cesantia_vejez",
        "guarderias",
    }
    total = sum(Decimal(row["amount"]["amount"]) for row in breakdown["branches"])
    assert total == Decimal(breakdown["total"]["amount"])


def test_the_cuota_fija_does_not_move_with_the_sbc():
    rule = registry.get("mx.imss.employer_quotas")
    low = {r["branch"]: r for r in rule.breakdown(sbc_daily="400", days="30")["branches"]}
    high = {r["branch"]: r for r in rule.breakdown(sbc_daily="900", days="30")["branches"]}
    assert low["em_especie_cuota_fija"]["amount"] == high["em_especie_cuota_fija"]["amount"]
    assert low["em_dinero"]["amount"] != high["em_dinero"]["amount"]


def test_employee_quotas_use_the_worker_side_rates():
    quotas = employee_imss_quotas(Decimal("500"), Decimal("30"))
    assert quotas["cesantia_vejez"] == (Decimal("500") * 30 * K.CV_EMPLOYEE.value).quantize(Decimal("0.01"))
    assert quotas["invalidez_vida"] == (Decimal("500") * 30 * K.IV_EMPLOYEE.value).quantize(Decimal("0.01"))


def test_infonavit_is_five_percent_of_the_capped_base():
    result = registry.get("mx.infonavit.employer").compute(sbc_daily="1000", days="30")
    assert result.value.amount == Decimal("1500.00")
    assert "29 fr. II" in result.explain.citations[0].article


def test_unverified_constants_are_named_and_marked():
    assert set(K.unverified()) == {
        "imss.cesantia_vejez.employer_table_2026",
        "isr.subsidio_empleo.monthly",
        "isr.subsidio_empleo.income_cap_monthly",
    }
    assert K.CV_EMPLOYER_TABLE_2026.mark == " (verify)"
    assert K.ISN_RATE.mark == ""


def test_every_constant_carries_a_citation_url():
    for const in K.ALL:
        assert const.source_url.startswith("https://"), const.key
        assert const.citation.article, const.key


def test_a_float_input_is_refused():
    with pytest.raises(TypeError):
        registry.get("mx.nl.isn").compute(payroll=1000.5)
