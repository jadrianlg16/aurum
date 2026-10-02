from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.ledger.base import LedgerStore, Posting, Transaction


def post(ledger: LedgerStore, ws: str, d: date, payee: str, expense_account: str, amount: str,
          asset_account: str = "Assets:Bank:Checking", meta: dict | None = None) -> str:
    return ledger.append(
        ws,
        Transaction(
            date=d,
            payee=payee,
            narration=payee,
            postings=[
                Posting(account=expense_account, amount=Amount(amount=amount)),
                Posting(account=asset_account),
            ],
            meta=meta or {},
        ),
    )


def income(ledger: LedgerStore, ws: str, d: date, payee: str, income_account: str, amount: str,
           asset_account: str = "Assets:Bank:Checking") -> str:
    return ledger.append(
        ws,
        Transaction(
            date=d,
            payee=payee,
            narration=payee,
            postings=[
                Posting(account=asset_account, amount=Amount(amount=amount)),
                Posting(account=income_account),
            ],
        ),
    )
