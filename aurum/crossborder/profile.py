"""The cross-border profile: the facts the ``xb.*`` rules need, stored on the workspace.

Persisted at ``workspace.profile["crossborder"]`` so it travels with the workspace JSON file and is
masked by ``Workspace.masked()`` like the rest of the profile. Days and balances are the only numbers;
everything else is a yes/no or a country code.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..core.money import DecimalStr
from ..core.workspaces import Workspace, get_workspace, save_workspace

PROFILE_KEY = "crossborder"
COUNTRIES = {"MX", "US"}


class IncomeSource(BaseModel):
    country: str
    kind: str = "self_employment"
    amount: DecimalStr = Decimal("0")
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError("amount must be Decimal/str/int, not float")
        return Decimal(str(v if v not in (None, "") else 0))


class ForeignAccount(BaseModel):
    country: str
    institution: str | None = None
    max_balance_usd: DecimalStr = Decimal("0")

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("max_balance_usd", mode="before")
    @classmethod
    def _balance(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError("max_balance_usd must be Decimal/str/int, not float")
        value = Decimal(str(v if v not in (None, "") else 0))
        if value < 0:
            raise ValueError("max_balance_usd must not be negative")
        return value


class CrossBorderProfile(BaseModel):
    days_mx: int = 0
    days_us: int = 0
    days_us_prior_1: int = 0
    days_us_prior_2: int = 0
    days_abroad_for_feie: int = 0
    bona_fide_resident_abroad: bool = False
    home_mx: bool = False
    home_us: bool = False
    green_card: bool = False
    citizenship: list[str] = Field(default_factory=list)
    filing_status: Literal["single", "mfj", "mfs", "hoh"] = "single"
    main_professional_center: str | None = None
    mx_source_income_share: DecimalStr | None = None
    foreign_tax_paid_usd: DecimalStr = Decimal("0")
    income_sources: list[IncomeSource] = Field(default_factory=list)
    foreign_accounts: list[ForeignAccount] = Field(default_factory=list)
    treaty_permanent_home: str | None = None
    treaty_center_of_vital_interests: str | None = None
    treaty_habitual_abode: str | None = None
    treaty_nationality: str | None = None

    @field_validator("days_mx", "days_us", "days_us_prior_1", "days_us_prior_2", "days_abroad_for_feie")
    @classmethod
    def _days(cls, v: int) -> int:
        if not 0 <= v <= 366:
            raise ValueError("day counts must be between 0 and 366")
        return v

    @field_validator("citizenship")
    @classmethod
    def _citizenship(cls, v: list[str]) -> list[str]:
        return [c.strip().upper() for c in v if c and c.strip()]

    @field_validator(
        "main_professional_center",
        "treaty_permanent_home",
        "treaty_center_of_vital_interests",
        "treaty_habitual_abode",
        "treaty_nationality",
    )
    @classmethod
    def _country_or_none(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        code = str(v).strip().upper()
        if code not in COUNTRIES:
            raise ValueError(f"expected one of {sorted(COUNTRIES)}, got {v!r}")
        return code

    @field_validator("mx_source_income_share", mode="before")
    @classmethod
    def _share(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        if isinstance(v, float):
            raise TypeError("mx_source_income_share must be Decimal/str/int, not float")
        share = Decimal(str(v))
        if not Decimal("0") <= share <= Decimal("1"):
            raise ValueError("mx_source_income_share is a fraction between 0 and 1")
        return share

    @field_validator("foreign_tax_paid_usd", mode="before")
    @classmethod
    def _tax(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError("foreign_tax_paid_usd must be Decimal/str/int, not float")
        return Decimal(str(v if v not in (None, "") else 0))

    def foreign_earned_income_usd(self) -> Decimal:
        """Non-US-source income, used as the § 911 base. USD sources only — FX is out of scope here."""
        return sum(
            (s.amount for s in self.income_sources if s.country != "US" and s.currency == "USD"),
            Decimal("0"),
        )

    def days_total(self) -> int:
        return self.days_mx + self.days_us


def load(ws_id: str) -> tuple[Workspace, CrossBorderProfile | None]:
    ws = get_workspace(ws_id)
    raw = (ws.profile or {}).get(PROFILE_KEY)
    return ws, (CrossBorderProfile.model_validate(raw) if raw else None)


def store(ws_id: str, profile: CrossBorderProfile) -> CrossBorderProfile:
    ws = get_workspace(ws_id)
    ws.profile = {**(ws.profile or {}), PROFILE_KEY: profile.model_dump(mode="json")}
    save_workspace(ws)
    return profile
