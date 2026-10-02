"""Round-trip property test: random valid transactions appended to a real
BeancountLedger come back from ``journal()`` equal, balance to zero per currency, and load with 0 errors.

Reverting ``q2`` in ``_fmt_amount`` (``f"{amount:.2f}"`` on an unquantized Decimal rounds HALF_EVEN and
the balancing leg is computed on unquantized values) makes ``test_random_txns_round_trip`` fail on the
per-currency-sum / balances-zero assertions.
"""

from __future__ import annotations

import string
from datetime import date
from decimal import Decimal

from beancount import loader
from hypothesis import given, settings
from hypothesis import strategies as st

from aurum.core.money import Amount, q2
from aurum.ledger.base import Posting, Transaction
from aurum.ledger.beancount_store import BeancountLedger

_ROOTS = ("Assets", "Liabilities", "Equity", "Income", "Expenses")
_COMPONENT = st.from_regex(r"[A-Z][A-Za-z0-9\-]{0,11}", fullmatch=True)
_ACCOUNT = st.tuples(st.sampled_from(_ROOTS), st.lists(_COMPONENT, min_size=1, max_size=3)).map(
    lambda t: ":".join([t[0], *t[1]])
)
_TEXT_ALPHABET = string.ascii_letters + string.digits + " '\"\\áéíóúñÑ€$#^:,.-_"
_TEXT = st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=40)
_TAG = st.from_regex(r"[A-Za-z0-9\-_/.]{1,12}", fullmatch=True)
# 3 decimals on purpose: HALF_UP (q2) and "%.2f" (HALF_EVEN) disagree on x.xx5, and the balancing leg
# must be computed on quantized values — both are what the q2 contract pins.
_CENTS = st.decimals(min_value=Decimal("-1e9"), max_value=Decimal("1e9"), places=3, allow_nan=False, allow_infinity=False)
_DATE = st.dates(min_value=date(2000, 1, 2), max_value=date(2035, 12, 31))
_CURRENCY = st.sampled_from(["MXN", "USD", "EUR"])


@st.composite
def transactions(draw) -> Transaction:
    n = draw(st.integers(min_value=1, max_value=4))
    accounts = draw(st.lists(_ACCOUNT, min_size=n + 1, max_size=n + 1, unique=True))
    currency = draw(_CURRENCY)
    explicit = [Posting(account=a, amount=Amount(amount=draw(_CENTS), currency=currency)) for a in accounts[:n]]
    balancing = Posting(account=accounts[n])  # one balancing leg
    postings = [*explicit, balancing]
    payee = draw(st.one_of(st.none(), _TEXT))
    return Transaction(
        date=draw(_DATE),
        payee=payee or None,
        narration=draw(_TEXT),
        postings=postings,
        tags=draw(st.lists(_TAG, max_size=3, unique=True)),
        links=[],
        meta={k: v for k, v in draw(st.dictionaries(st.from_regex(r"[a-z][a-z0-9_]{1,8}", fullmatch=True), _TEXT, max_size=2)).items()},
    )


def _expected_postings(txn: Transaction) -> tuple:
    """The contract: explicit amounts are quantized HALF_UP first, then the balancing leg is derived."""
    quantized = txn.model_copy(
        update={"postings": [p.model_copy(update={"amount": p.amount.quantized()}) if p.amount else p for p in txn.postings]}
    )
    return tuple(sorted((p.account, p.amount.amount, p.amount.currency) for p in quantized.balanced() if p.amount))


def _canon(txn: Transaction, *, expected: bool = False) -> tuple:
    postings = (
        _expected_postings(txn)
        if expected
        else tuple(sorted((p.account, p.amount.amount, p.amount.currency) for p in txn.postings if p.amount))
    )
    return (txn.date, txn.payee or None, txn.narration, frozenset(txn.tags), postings, tuple(sorted(txn.meta.items())))


@settings(max_examples=200, deadline=None)
@given(st.lists(transactions(), min_size=1, max_size=5))
def test_random_txns_round_trip(tmp_path_factory, txns: list[Transaction]):
    root = tmp_path_factory.mktemp("rt")
    ledger = BeancountLedger(data_dir=root)
    ids = [ledger.append("ws1", t) for t in txns]
    assert len(set(ids)) == len(ids)

    stored = ledger.journal("ws1")
    assert len(stored) == len(txns)
    by_id = {t.links[0]: t for t in stored}
    for txn_id, original in zip(ids, txns, strict=True):
        got = by_id[txn_id]
        assert _canon(got) == _canon(original, expected=True)
        assert got.links == [txn_id]
        totals: dict[str, Decimal] = {}
        for p in got.postings:
            assert p.amount is not None
            totals[p.amount.currency] = totals.get(p.amount.currency, Decimal(0)) + p.amount.amount
        assert all(v == 0 for v in totals.values()), totals

    _entries, errors, _ = loader.load_file(str(ledger.main_path("ws1")))
    assert errors == []
    for amounts in ledger.balances("ws1").values():
        for a in amounts:
            assert a.amount == q2(a.amount)
