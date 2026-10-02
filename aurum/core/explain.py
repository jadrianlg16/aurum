"""Explain: the payload behind every figure — one line, worked steps, citations, rule versions.

Math lives in code (see docs/ARCHITECTURE.md): models never compute a figure. Rules produce Explain
objects; the UI renders them at three depths (summary → steps → citations). Citations carry a trust tier
and an "as of" range.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

TrustTier = Literal["primary", "official_guidance", "professional", "blog"]


class Citation(BaseModel):
    law: str
    article: str
    url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    trust_tier: TrustTier = "primary"
    excerpt: str | None = None

    def label(self) -> str:
        return f"{self.law} art. {self.article}" if self.article else self.law


class Step(BaseModel):
    label: str
    formula: str | None = None
    value: str
    id: str | None = None


class Explain(BaseModel):
    summary: str
    steps: list[Step] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    rule_versions: list[str] = Field(default_factory=list)
    confidence: float | None = None

    def add_step(
        self, label: str, value: object, formula: str | None = None, *, id: str | None = None  # noqa: A002
    ) -> Explain:
        """``id`` defaults to ``label`` when unset and ``label`` already looks like an id
        (``^[a-z][a-z0-9_]*$``) — additive: ``label`` is untouched, so every
        existing caller and the i18n sweep keep passing unchanged."""
        if id is None and _ID_RE.match(label):
            id = label  # noqa: A001
        self.steps.append(Step(label=label, formula=formula, value=str(value), id=id))
        return self
