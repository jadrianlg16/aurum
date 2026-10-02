"""Plan scenarios. Each module exposes ``Inputs`` (pydantic) and ``run(inputs)``.

``run(inputs)`` always returns ``{"inputs": ..., "results": ..., "explain": Explain}``.
"""

from __future__ import annotations

from . import buy_vs_rent, cash_vs_credit, debt_payoff, entity_us, regime_mx, retirement

SCENARIOS = {
    "regime_mx": regime_mx,
    "entity_us": entity_us,
    "buy_vs_rent": buy_vs_rent,
    "cash_vs_credit": cash_vs_credit,
    "retirement": retirement,
    "debt_payoff": debt_payoff,
}

__all__ = ["SCENARIOS"]
