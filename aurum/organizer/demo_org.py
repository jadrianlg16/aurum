"""Demo data for the money organizer: recurring charges the detector must find.

``seed_demo_org("demo-mx")`` writes the same charges into **both** ``ingest_bank_lines`` and the
ledger — that is what the real world looks like once a statement has been imported and reconciled,
and it exercises the detector's de-duplication. Everything is anchored to ``today`` so the trial and
"next 7 days" alerts are live whenever the demo is rebuilt, and everything is idempotent (bank lines
dedupe on their hash; the ledger dedupes on the ``links`` id).

Seeded (all synthetic):

===========================  =========  ===========  ================================================
Netflix                      219 MXN    monthly      199 → 219 three months ago: price-increase alert
Spotify                      129 MXN    monthly
Telcel                       399 MXN    monthly
CFE                          890/1,120  bimonthly    variable amount (utility band)
Renta                        12,000     monthly      day 1
Smart Fit                    649        monthly
iCloud                       49         monthly
Amazon Prime                 899        annual       two renewals, 365 days apart
Crédito automotriz           from pf    monthly      linked to the demo ``Liabilities:Loans:Auto`` loan
Nómina Acme                  45,000     monthly      income, day 5
Cliente Delta (freelance)    18,000     monthly      income, day 20
Max (trial)                  249        monthly      commitment with ``trial_ends = today + 5 days``
===========================  =========  ===========  ================================================
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from ..core.db import connect
from ..core.money import Amount
from ..ledger.base import Posting, Transaction, get_ledger
from . import cadence as cad
from . import commitments as cmt
from .models import CommitmentIn

BANK = "BBVA"
CURRENCY = "MXN"
CASH_ACCOUNT = "Assets:Bank:BBVA"

# (key, description, expense/income account, amounts newest-first per month, day, months_back)
MONTHLY_OUT: list[tuple[str, str, str, list[str], int]] = [
    ("netflix", "NETFLIX.COM 866-579-7172 CIUDAD DE MEX", "Expenses:Personal:Entertainment",
     ["199", "199", "219"], 15),
    ("spotify", "SPOTIFY P0A1B2C3 MX", "Expenses:Personal:Entertainment", ["129", "129", "129"], 8),
    ("telcel", "SPEI ENVIADO TELCEL 0341", "Expenses:Housing:Internet", ["399", "399", "399"], 12),
    ("renta", "PAGO RENTA DEPARTAMENTO", "Expenses:Housing:RentMortgage",
     ["10500", "10500", "10500"], 1),
    ("gym", "SMART FIT CENTRO SUC 0001", "Expenses:Personal:Entertainment", ["649", "649", "649"], 5),
    ("icloud", "APPLE.COM/BILL ICLOUD 800-676-2775", "Expenses:Work:Software", ["49", "49", "49"], 20),
    ("auto", "CARGO CREDITO AUTOMOTRIZ BBVA", "Expenses:Other", ["4918.77", "4918.77", "4918.77"], 18),
]

MONTHLY_IN: list[tuple[str, str, str, list[str], int]] = [
    ("nomina", "DEPOSITO NOMINA ACME SA DE CV", "Income:Salary", ["45000", "45000", "45000"], 5),
    ("freelance", "SPEI RECIBIDO CLIENTE DELTA", "Income:Freelance", ["18000", "18000", "18000"], 20),
]


def _recent_dates(today: date, day: int, count: int) -> list[date]:
    """The ``count`` most recent occurrences of day-of-month ``day`` at or before ``today``, oldest first.

    Anchoring on *past* dates (rather than a fixed number of months back) keeps the demo consistent
    whenever it is rebuilt: every charge whose day has already passed this month is present and paid.
    """
    latest = cad.clamp_day(today.year, today.month, day)
    if latest > today:
        previous = today - relativedelta(months=1)
        latest = cad.clamp_day(previous.year, previous.month, day)
    out = [latest]
    for _ in range(count - 1):
        prev = out[-1] - relativedelta(months=1)
        out.append(cad.clamp_day(prev.year, prev.month, day))
    return list(reversed(out))


def _bank_line(conn, ws_id: str, day: date, description: str, amount: Decimal) -> None:
    from ..ingest.bank_csv import line_hash

    conn.execute(
        "INSERT OR IGNORE INTO ingest_bank_lines (ws_id, bank, date, description, amount, currency, "
        "balance, hash, imported_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (ws_id, BANK, day.isoformat(), description, str(amount), CURRENCY, None,
         line_hash(ws_id, BANK, day, description, amount), datetime.now(UTC).isoformat(timespec="seconds")),
    )


def _ledger_txn(ledger, ws_id: str, key: str, day: date, description: str, account: str,
                amount: Decimal, direction: str) -> str:
    txn_id = f"org-demo-{key}-{day.isoformat()}"
    if direction == "out":
        postings = [
            Posting(account=account, amount=Amount(amount=amount, currency=CURRENCY)),
            Posting(account=CASH_ACCOUNT, amount=Amount(amount=-amount, currency=CURRENCY)),
        ]
    else:
        postings = [
            Posting(account=CASH_ACCOUNT, amount=Amount(amount=amount, currency=CURRENCY)),
            Posting(account=account, amount=Amount(amount=-amount, currency=CURRENCY)),
        ]
    ledger.append(
        ws_id,
        Transaction(date=day, payee=description, narration="demo organizer",
                    postings=postings, tags=["demo", "organizer"],
                    links=[txn_id], meta={"source": "demo-organizer"}),
    )
    return txn_id


def seed_demo_org(ws_id: str = "demo-mx", today: date | None = None) -> dict:
    """Seed the recurring demo movements. Idempotent; returns what it wrote."""
    today = today or date.today()
    conn = connect()
    ledger = get_ledger()
    existing_links = set()
    try:
        for txn in ledger.journal(ws_id):
            existing_links.update(txn.links or [])
    except Exception:  # noqa: BLE001 — empty ledger
        pass

    written = {"bank_lines": 0, "ledger_txns": 0, "commitments": 0}

    def post(key: str, day: date, description: str, account: str, amount: Decimal, direction: str) -> None:
        signed = amount if direction == "in" else -amount
        _bank_line(conn, ws_id, day, description, signed)
        written["bank_lines"] += 1
        txn_id = f"org-demo-{key}-{day.isoformat()}"
        if txn_id not in existing_links:
            _ledger_txn(ledger, ws_id, key, day, description, account, amount, direction)
            existing_links.add(txn_id)
            written["ledger_txns"] += 1

    # the three most recent monthly charges, oldest first (so the last amount is the current price)
    for direction, table in (("out", MONTHLY_OUT), ("in", MONTHLY_IN)):
        for key, description, account, amounts, day in table:
            for when, raw in zip(_recent_dates(today, day, len(amounts)), amounts, strict=True):
                post(key, when, description, account, Decimal(raw), direction)

    # CFE: bimonthly, variable amount (consumption)
    for offset, raw in ((118, "890"), (58, "1120")):
        post("cfe", today - timedelta(days=offset), "CFE SSC 9876543210",
             "Expenses:Housing:Utilities", Decimal(raw), "out")

    # Amazon Prime: annual, two renewals exactly 365 days apart
    for offset in (395, 30):
        post("prime", today - timedelta(days=offset), "AMAZON PRIME*2X4Y5 MX",
             "Expenses:Personal:Entertainment", Decimal("899"), "out")

    conn.commit()

    # A live trial the alerts must catch (a commitment, not a charge: nothing has been billed yet).
    if not any(c.name == "Max" for c in cmt.list_commitments(ws_id)):
        cmt.create(
            ws_id,
            CommitmentIn(
                kind="subscription", name="Max", merchant_patterns=["MAX"],
                amount=Amount(amount=Decimal("249"), currency=CURRENCY),
                cadence="monthly", anchor_day=(today + timedelta(days=5)).day,
                next_due=today + timedelta(days=5), account=CASH_ACCOUNT, essential="wants",
                status="trial", trial_ends=today + timedelta(days=5), started=today - timedelta(days=25),
                source="manual", confidence=1.0, category_hint="streaming",
            ),
            today=today,
        )
        written["commitments"] += 1
    return written
