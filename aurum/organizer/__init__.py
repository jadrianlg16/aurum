"""Money organizer — "Mi dinero".

Subscriptions, bills and loan payments detected from the ledger and bank lines, a bills calendar, a
90-day cash-flow forecast with "safe to spend until payday", and an envelope spending plan. Every
figure is computed in code and carries an ``Explain``; no LLM is used anywhere in this module.
"""

from __future__ import annotations

__all__ = ["router"]
