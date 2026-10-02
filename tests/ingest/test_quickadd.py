"""Quick-add: the parser resolves a pf account and previews a real entry; the legacy
``parse_quickadd`` wrapper keeps the Telegram/inbox path alive."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aurum.ingest import quickadd
from aurum.ingest.quickadd import NoAccount, parse_entry, parse_quickadd
from aurum.pf import accounts_admin

WS = "demo"


def _account(name="Efectivo", type_="cash", institution=None, ws=WS):
    return accounts_admin.create_account(
        ws, accounts_admin.AccountIn(name=name, type=type_, institution=institution)
    )


def test_parse_text_finds_the_amount_anywhere():
    parsed = quickadd.parse_text("viaje a europa 900")
    assert parsed.amount == Decimal("900.00") and parsed.words == ["viaje", "a", "europa"]
    parsed = quickadd.parse_text("1,200 uber trabajo")
    assert parsed.amount == Decimal("1200.00")
    parsed = quickadd.parse_text("$89.99 USD spotify")
    assert parsed.amount == Decimal("89.99") and parsed.currency == "USD" and parsed.words == ["spotify"]


def test_single_cash_account_is_the_default_and_label_matches_whole_words():
    cash = _account()
    preview = parse_entry(WS, "250 tacos comida")
    assert preview.entry.account_id == cash["id"] and preview.account_name == "Efectivo"
    assert preview.entry.kind == "expense" and preview.entry.amount.amount == Decimal("250.00")
    assert preview.label_name == "Comida fuera"
    assert preview.entry.payee == "tacos"
    assert preview.entry.source == "quickadd"


def test_viaje_a_europa_never_matches_ropa():
    _account()
    preview = parse_entry(WS, "viaje a europa 900")
    assert preview.label_name != "Ropa"
    assert preview.label_name == "Viajes"


def test_account_word_match_on_name_or_institution():
    _account("Efectivo", "cash")
    card = _account("Tarjeta Oro", "credit_card", institution="Banorte")
    preview = parse_entry(WS, "89.99 spotify suscripcion tarjeta")
    assert preview.entry.account_id == card["id"]
    assert "tarjeta" not in (preview.entry.payee or "")
    preview = parse_entry(WS, "500 super banorte")
    assert preview.entry.account_id == card["id"] and preview.label_name == "Súper"


def test_explicit_account_id_wins_and_unknown_is_a_key_error():
    _account("Efectivo", "cash")
    bank = _account("BBVA", "checking")
    preview = parse_entry(WS, "250 tacos comida", account_id=bank["id"])
    assert preview.entry.account_id == bank["id"]
    with pytest.raises(KeyError):
        parse_entry(WS, "250 tacos comida", account_id="nope")


def test_no_account_resolvable_raises_no_account():
    with pytest.raises(NoAccount):
        parse_entry(WS, "250 tacos comida")
    _account("A", "checking")
    _account("B", "checking")  # two candidates: ambiguous → still NoAccount
    with pytest.raises(NoAccount):
        parse_entry(WS, "250 tacos comida")


def test_negative_amount_or_income_word_means_income_and_drops_expense_labels():
    _account()
    preview = parse_entry(WS, "-500 cliente pago factura")
    assert preview.entry.kind == "income"
    preview = parse_entry(WS, "500 deposito nomina")
    assert preview.entry.kind == "income" and preview.label_name == "Sueldo/Nómina"
    preview = parse_entry(WS, "ingreso 300 comida")
    assert preview.entry.kind == "income" and preview.entry.label_id is None
    assert any("Comida fuera" in w for w in preview.warnings)


def test_legacy_wrapper_uses_the_pf_account_when_there_is_one():
    cash = _account()
    result = parse_quickadd("250 tacos comida", ws_id=WS)
    accounts = {p.account: p.amount for p in result.transaction.postings}
    assert accounts[cash["account"]].amount == Decimal("-250.00")
    assert "Expenses:Food:DiningOut" in accounts


def test_legacy_wrapper_falls_back_to_assets_cash_without_accounts():
    result = parse_quickadd("250 tacos comida", ws_id="no-accounts-ws")
    txn = result.transaction
    assert txn.narration == "250 tacos comida"
    amounts = {p.account: p.amount for p in txn.postings}
    assert amounts["Assets:Cash"].amount == Decimal("-250.00")
    assert "Expenses:Food:DiningOut" in amounts  # labels are seeded per workspace
    income = parse_quickadd("-500 cliente pago factura", ws_id="no-accounts-ws")
    cash_leg = next(p for p in income.transaction.postings if p.account == "Assets:Cash")
    assert cash_leg.amount.amount == Decimal("500.00")


def test_empty_text_raises():
    with pytest.raises(ValueError):
        parse_quickadd("   ", ws_id=WS)
    with pytest.raises(ValueError):
        quickadd.parse_text("tacos sin monto")
