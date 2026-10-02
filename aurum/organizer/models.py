"""Pydantic shapes for the money organizer."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from ..core.explain import Explain
from ..core.money import Amount
from ..core.validation import DayOfMonth, PositiveInt, Weekday

Kind = Literal[
    "subscription", "bill", "utility", "rent", "insurance",
    "loan_payment", "tax", "income", "transfer", "other",
]
Cadence = Literal[
    "weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "annual", "custom",
]
Essential = Literal["needs", "wants", "savings", "debt"]
Status = Literal["active", "paused", "cancelled", "trial"]
OccurrenceStatus = Literal["upcoming", "due", "paid", "missed", "skipped"]
AlertKind = Literal[
    "price_increase", "price_decrease", "trial_ending", "missed_payment",
    "upcoming", "duplicate", "annual_renewal", "forgotten",
    "income_expected", "income_late", "income_changed", "cancelled_still_charging",
]
Severity = Literal["info", "warn", "urgent"]
Source = Literal["detected", "manual", "imported"]


def _non_negative(value: Amount) -> Amount:
    if value.amount < 0:
        raise ValueError("amount must be 0 or more")
    return value


NonNegativeAmount = Annotated[Amount, AfterValidator(_non_negative)]


class Commitment(BaseModel):
    id: str = ""
    ws_id: str = ""
    kind: Kind = "subscription"
    name: str
    merchant_patterns: list[str] = Field(default_factory=list)
    amount: Amount
    amount_variable: bool = False
    cadence: Cadence = "monthly"
    interval_days: int | None = None
    anchor_day: int | None = None
    weekday: int | None = None
    next_due: date
    account: str = "Assets:Bank"
    account_id: str | None = None
    label_id: str | None = None
    essential: Essential = "needs"
    status: Status = "active"
    trial_ends: date | None = None
    started: date | None = None
    ended: date | None = None
    auto_pay: bool = False
    cancel_notes: str | None = None
    linked_loan_id: str | None = None
    linked_card_id: str | None = None
    source: Source = "manual"
    confidence: float = 1.0
    last_seen: date | None = None
    notes: str | None = None
    category_hint: str | None = None
    reviewed_at: date | None = None
    explain: Explain | None = None


class CommitmentIn(BaseModel):
    """Write shape: ``next_due`` may be omitted and is then projected from the cadence anchors.

    ``account_id`` (a pf account) wins over ``account`` (a ledger name); with neither the legacy
    default ``Assets:Bank`` applies. ``force`` skips the duplicate-name guard and is never stored.
    Bounds (anchor_day 1..31, weekday 0..6, interval_days ≥ 1, amount ≥ 0) are 422s, never 500s.
    """

    kind: Kind = "subscription"
    name: str = Field(min_length=1, max_length=120)
    merchant_patterns: list[str] = Field(default_factory=list)
    amount: NonNegativeAmount
    amount_variable: bool = False
    cadence: Cadence = "monthly"
    interval_days: PositiveInt | None = None
    anchor_day: DayOfMonth | None = None
    weekday: Weekday | None = None
    next_due: date | None = None
    account: str | None = None
    account_id: str | None = None
    label_id: str | None = None
    essential: Essential = "needs"
    status: Status = "active"
    trial_ends: date | None = None
    started: date | None = None
    ended: date | None = None
    auto_pay: bool = False
    cancel_notes: str | None = None
    linked_loan_id: str | None = None
    linked_card_id: str | None = None
    source: Source = "manual"
    confidence: float = 1.0
    last_seen: date | None = None
    notes: str | None = None
    category_hint: str | None = None
    force: bool = False


class CommitmentPatch(BaseModel):
    """``PUT /commitments/{id}`` body: every field optional, **no defaults applied** — only the keys
    present in the request (``model_dump(exclude_unset=True)``) touch the stored row."""

    kind: Kind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    merchant_patterns: list[str] | None = None
    amount: NonNegativeAmount | None = None
    amount_variable: bool | None = None
    cadence: Cadence | None = None
    interval_days: PositiveInt | None = None
    anchor_day: DayOfMonth | None = None
    weekday: Weekday | None = None
    next_due: date | None = None
    account: str | None = None
    account_id: str | None = None
    label_id: str | None = None
    essential: Essential | None = None
    status: Status | None = None
    trial_ends: date | None = None
    started: date | None = None
    ended: date | None = None
    auto_pay: bool | None = None
    cancel_notes: str | None = None
    linked_loan_id: str | None = None
    linked_card_id: str | None = None
    source: Source | None = None
    confidence: float | None = None
    last_seen: date | None = None
    notes: str | None = None
    category_hint: str | None = None
    force: bool | None = None


class Occurrence(BaseModel):
    commitment_id: str
    due: date
    amount: Amount
    status: OccurrenceStatus = "upcoming"
    txn_id: str | None = None
    entry_id: str | None = None
    auto_created: bool = False


class Alert(BaseModel):
    id: str
    kind: AlertKind
    severity: Severity = "info"
    commitment_id: str | None = None
    title: str
    body: str
    old_amount: Amount | None = None
    new_amount: Amount | None = None
    due: date | None = None
    explain: Explain | None = None


class Evidence(BaseModel):
    date: date
    amount: Amount
    description: str
    source: str = "bank"


class Candidate(BaseModel):
    id: str
    merchant: str
    preview: Commitment
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = 0.0
    status: Literal["open", "accepted", "dismissed"] = "open"
    flags: list[str] = Field(default_factory=list)
    existing_commitment_id: str | None = None
