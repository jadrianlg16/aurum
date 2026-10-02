import pytest

from aurum.ledger.base import validate_account


@pytest.mark.parametrize(
    "name",
    [
        "Assets:Bank:BBVA",
        "Expenses:Food:DiningOut",
        "Liabilities:CreditCard:Nu",
        "Income:Salary",
        "Equity:Opening",
    ],
)
def test_valid_accounts(name):
    assert validate_account(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "Expenses:comida",
        "Gastos:Comida",
        "Assets",
        "Assets:",
        'Assets:Bank\nplugin "x"',
        "",
        "Assets:Bank BBVA",
    ],
)
def test_invalid_accounts(name):
    with pytest.raises(ValueError):
        validate_account(name)
