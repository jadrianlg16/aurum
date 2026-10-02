"""GET /pf/{ws}/onboarding — resumable setup progress for a manual-first wizard.

Every step is computed from what already exists (accounts, income streams, recurring commitments, hand-
logged entries) so the UI wizard can be entered, left and re-entered at any point with no separate
"progress" state of its own to go stale.

Steps: ``accounts``, ``income``, ``recurring``, ``first_entries``. ``done`` = accounts.done AND
first_entries.done — an account and the first movement are the non-negotiable minimum ("create an account,
log a coffee, see the balance change"); income streams and recurring bills are useful but optional.
Import is not a step (a shortcut card on the done screen).
"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from . import accounts_admin, store, streams

router = APIRouter()

STEP_IDS = ("accounts", "income", "recurring", "first_entries")
_GATING_STEPS = {"accounts", "first_entries"}


def first_entries_count(ws_id: str) -> int:
    conn = store.db()
    row = conn.execute(
        "SELECT COUNT(*) FROM pf_entries WHERE ws_id=? AND source IN ('manual','quickadd') AND voided=0",
        (ws_id,),
    ).fetchone()
    return int(row[0])


def _recurring_count(ws_id: str) -> int:
    from ..organizer import commitments as org_commitments

    return sum(
        1 for c in org_commitments.list_commitments(ws_id, status="active") if c.kind != "income"
    )


def get_onboarding(ws_id: str, lang: str | None = None) -> dict:
    accounts_count = len(accounts_admin.list_rows(ws_id, include_archived=False))
    income_count = len(streams.list_streams(ws_id))
    recurring_count = _recurring_count(ws_id)
    entries_count = first_entries_count(ws_id)
    language = ws_lang(ws_id, lang)

    steps = [
        {"id": "accounts", "done": accounts_count > 0, "count": accounts_count,
         "hint": i18n_t("pf.onboarding.accounts", language)},
        {"id": "income", "done": income_count > 0, "count": income_count,
         "hint": i18n_t("pf.onboarding.income", language)},
        {"id": "recurring", "done": recurring_count > 0, "count": recurring_count,
         "hint": i18n_t("pf.onboarding.recurring", language)},
        {"id": "first_entries", "done": entries_count > 0, "count": entries_count,
         "hint": i18n_t("pf.onboarding.first_entries", language)},
    ]
    done = all(s["done"] for s in steps if s["id"] in _GATING_STEPS)
    return {"steps": steps, "done": done}


@router.get("/{ws}/onboarding")
def api_onboarding(ws: str, lang: str | None = None) -> dict:
    return get_onboarding(ws, lang)
