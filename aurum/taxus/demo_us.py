"""Synthetic ``demo-us`` workspace: a Texas sole proprietor with one year of USD postings.

Called from ``aurum.demo.extras`` when the demo workspaces are built. Everything is
invented: no real client, bank, EIN or SSN ever enters this repo. The figures are chosen so the year
lands in the 22% federal bracket, well under every Texas franchise threshold, and so the cross-border
profile trips the FBAR flag and the dual-residency flag — the interesting cases are exercised.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..core.money import Amount
from ..core.workspaces import Workspace, get_workspace, save_workspace
from ..crossborder.profile import CrossBorderProfile
from ..crossborder.profile import store as store_crossborder
from ..ledger.base import Posting, Transaction

WS_ID = "demo-us"
CURRENCY = "USD"
YEAR = 2026

CHECKING = "Assets:US:Bank:Checking"
INCOME = "Income:US:Consulting"
INCOME_TRAINING = "Income:US:Training"
COGS = "Expenses:US:COGS:Subcontractors"

EXPENSES: list[tuple[str, str, str]] = [
    ("Expenses:US:Software", "2400.00", "SaaS subscriptions"),
    ("Expenses:US:Travel", "3150.00", "Client travel"),
    ("Expenses:US:Insurance", "1800.00", "Professional liability"),
    ("Expenses:US:Office", "960.00", "Coworking desk"),
    ("Expenses:US:Professional", "1500.00", "Bookkeeping and legal"),
]

# One invoice per month; the year totals USD 132,000 of consulting plus USD 9,000 of training.
MONTHLY_CONSULTING = Decimal("11000.00")
TRAINING = [(3, "4500.00"), (9, "4500.00")]
SUBCONTRACTOR = [(5, "6000.00"), (11, "6000.00")]
REFUND = (7, "1500.00")  # a returned engagement fee — Schedule C line 2


def _amount(value: str | Decimal) -> Amount:
    return Amount(amount=Decimal(str(value)), currency=CURRENCY)


def transactions() -> list[Transaction]:
    """The year's postings. Income accounts are credited (negative), expenses debited (positive)."""
    out: list[Transaction] = []
    for month in range(1, 13):
        day = date(YEAR, month, 20)
        out.append(
            Transaction(
                date=day,
                payee="Northwind Demo LLC",
                narration=f"Consulting retainer {day:%B %Y}",
                postings=[
                    Posting(account=CHECKING, amount=_amount(MONTHLY_CONSULTING)),
                    Posting(account=INCOME, amount=_amount(-MONTHLY_CONSULTING)),
                ],
                tags=["us"],
                links=[f"demo-us-consulting-{YEAR}-{month:02d}"],
                meta={"jurisdiction": "US", "source": "demo"},
            )
        )
    for month, value in TRAINING:
        day = date(YEAR, month, 8)
        out.append(
            Transaction(
                date=day,
                payee="Rio Grande Demo Co",
                narration="Training workshop",
                postings=[
                    Posting(account=CHECKING, amount=_amount(value)),
                    Posting(account=INCOME_TRAINING, amount=_amount("-" + value)),
                ],
                tags=["us"],
                links=[f"demo-us-training-{YEAR}-{month:02d}"],
                meta={"jurisdiction": "US", "source": "demo"},
            )
        )
    month, value = REFUND
    out.append(
        Transaction(
            date=date(YEAR, month, 3),
            payee="Northwind Demo LLC",
            narration="Refund of an engagement fee (Schedule C line 2)",
            postings=[
                Posting(account=INCOME, amount=_amount(value)),
                Posting(account=CHECKING, amount=_amount("-" + value)),
            ],
            tags=["us"],
            links=[f"demo-us-refund-{YEAR}-{month:02d}"],
            meta={"jurisdiction": "US", "source": "demo"},
        )
    )
    for month, value in SUBCONTRACTOR:
        out.append(
            Transaction(
                date=date(YEAR, month, 25),
                payee="Demo Subcontractor",
                narration="Subcontracted delivery (cost of goods sold)",
                postings=[
                    Posting(account=COGS, amount=_amount(value)),
                    Posting(account=CHECKING, amount=_amount("-" + value)),
                ],
                tags=["us"],
                links=[f"demo-us-cogs-{YEAR}-{month:02d}"],
                meta={"jurisdiction": "US", "source": "demo"},
            )
        )
    for account, value, narration in EXPENSES:
        for month in (2, 8):
            half = (Decimal(value) / 2).quantize(Decimal("0.01"))
            out.append(
                Transaction(
                    date=date(YEAR, month, 12),
                    payee="Demo Vendor",
                    narration=narration,
                    postings=[
                        Posting(account=account, amount=_amount(half)),
                        Posting(account=CHECKING, amount=_amount(-half)),
                    ],
                    tags=["us"],
                    links=[f"demo-us-{account.split(':')[-1].lower()}-{YEAR}-{month:02d}"],
                    meta={"jurisdiction": "US", "source": "demo"},
                )
            )
    return sorted(out, key=lambda t: t.date)


def crossborder_profile() -> CrossBorderProfile:
    """An invented US citizen consultant who lives in Mexico most of the year and keeps a Texas practice —
    deliberately a dual-residency case."""
    return CrossBorderProfile(
        days_mx=210,
        days_us=150,
        days_us_prior_1=150,
        days_us_prior_2=150,
        days_abroad_for_feie=210,
        bona_fide_resident_abroad=False,
        home_mx=True,
        home_us=True,
        green_card=False,
        citizenship=["US"],
        filing_status="single",
        main_professional_center="MX",
        mx_source_income_share="0.20",  # under 50%, so residency turns on the professional centre
        foreign_tax_paid_usd="1800.00",
        income_sources=[
            {"country": "US", "kind": "self_employment", "amount": "132000.00", "currency": "USD"},
            {"country": "MX", "kind": "self_employment", "amount": "9000.00", "currency": "USD"},
        ],
        foreign_accounts=[
            {"country": "MX", "institution": "Banco Demo Uno", "max_balance_usd": "14500.00"},
            {"country": "MX", "institution": "Banco Demo Ahorro", "max_balance_usd": "2200.00"},
        ],
        treaty_permanent_home=None,
        treaty_center_of_vital_interests="MX",
        treaty_habitual_abode="MX",
        treaty_nationality=None,
    )


def build_demo_us(data_dir: str | Path | None = None, force: bool = False) -> dict[str, Any]:
    """Create the ``demo-us`` workspace. Idempotent: an existing manifest is returned untouched."""
    if data_dir is not None:
        os.environ["AURUM_DATA_DIR"] = str(data_dir)

    from ..core.config import settings
    from ..ledger.base import get_ledger

    ws_dir = settings().workspace_dir(WS_ID)
    manifest_path = ws_dir / "docs" / "demo-us-manifest.json"
    if manifest_path.exists() and not force:
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        get_workspace(WS_ID)
    except Exception:  # noqa: BLE001 — WorkspaceNotFound, or an unreadable file we are replacing
        save_workspace(
            Workspace(
                id=WS_ID,
                name="Demo USA (Texas sole proprietor)",
                kind="personal",
                jurisdictions=["US"],
                base_currency=CURRENCY,
                language="en",
                profile={
                    "country": "US",
                    "state": "TX",
                    "entity_type": "sole_proprietorship",
                    "business_type": "other",
                    "demo": True,
                    "us": {
                        "filing_status": "single",
                        "prior_year_tax": "24000.00",
                        "prior_year_agi": "118000.00",
                        "withholding": "0",
                        "other_income": "0",
                    },
                },
            )
        )

    ledger = get_ledger()
    txns = transactions()
    for txn in txns:
        ledger.append(WS_ID, txn)

    store_crossborder(WS_ID, crossborder_profile())

    gross = Decimal("132000.00") + Decimal("9000.00")
    manifest = {
        "workspace": WS_ID,
        "year": YEAR,
        "currency": CURRENCY,
        "transactions_posted": len(txns),
        "expected": {
            "gross_receipts": str(gross),
            "returns_and_allowances": REFUND[1],
            "cost_of_goods_sold": str(sum(Decimal(v) for _, v in SUBCONTRACTOR)),
            "expenses": str(sum(Decimal(v) for _, v, _n in EXPENSES)),
        },
        "crossborder": {
            "fbar_expected": True,
            "dual_residency_expected": True,
            "note": (
                "two Mexican accounts peaking at USD 16,700 together (over the USD 10,000 threshold), and a "
                "US citizen whose main professional centre is in Mexico — so the treaty tie-breaker flag fires"
            ),
        },
        "endpoints": [
            f"/api/tax/us/{WS_ID}/{YEAR}",
            f"/api/tax/us/{WS_ID}/{YEAR}/organizer.pdf",
            f"/api/tax/us/{WS_ID}/{YEAR}/tx-franchise",
            f"/api/crossborder/{WS_ID}/assessment",
        ],
        "disclaimer": "Entirely synthetic. No real person, client, bank or account number.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
