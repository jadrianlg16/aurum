"""The bills calendar: one row per day, everything that moves money merged into it.

Sources merged (all defensive):

* projected **commitment** occurrences (including income) with their paid/unpaid status,
* pf **credit cards**: cut date and payment due date,
* pf **loans**: the monthly payment date, when no commitment already covers that loan,
* the **insights** deadline calendar for tax dates (``mx_*`` / ``us_*`` kinds only — the card rows
  there would duplicate the ones this module already produces), **only when the tax module is on**
  for the workspace (``core.workspaces.module_on(ws, "tax")``).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from . import commitments as cmt
from . import occurrences as occ
from . import pf_bridge


def _commitment_items(ws_id: str, start: date, end: date, today: date) -> list[dict]:
    out = []
    linked_loans: set[str] = set()
    txns = pf_bridge.live_txns(ws_id, start - timedelta(days=occ.DATE_WINDOW_DAYS),
                               end + timedelta(days=occ.DATE_WINDOW_DAYS))
    accounts = pf_bridge.accounts_index(ws_id)
    for c in cmt.list_commitments(ws_id):
        if c.status == "cancelled" and (c.ended is None or c.ended < start):
            continue
        if c.linked_loan_id:
            linked_loans.add(c.linked_loan_id)
        hit = accounts.get(c.account_id) if c.account_id else accounts.get(c.account)
        for o in occ.build(ws_id, c, start, end, today=today, txns=txns):
            out.append({
                "kind": "income" if c.kind == "income" else "commitment",
                "date": o.due.isoformat(),
                "id": c.id,
                "name": c.name,
                "amount": {"amount": str(q2(o.amount.amount)), "currency": o.amount.currency},
                "status": o.status,
                "txn_id": o.txn_id,
                "entry_id": o.entry_id,
                "account_id": hit["id"] if hit else c.account_id,
                "account_name": hit["name"] if hit else None,
                "direction": "in" if c.kind == "income" else "out",
                "commitment_kind": c.kind,
                # a fixed amount can be marked paid in one tap; a variable one is logged first
                "amount_variable": bool(c.amount_variable),
            })
    out.append({"_linked_loans": sorted(linked_loans)})  # sentinel, stripped by the caller
    return out


def _card_items(ws_id: str, start: date, end: date) -> list[dict]:
    try:
        from ..pf import credit
    except Exception:  # noqa: BLE001
        return []
    out = []
    try:
        cards = credit.list_cards(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for card in cards:
        try:
            status = credit.card_status(ws_id, card)
        except Exception:  # noqa: BLE001
            continue
        for key, kind in (("next_cut_date", "card_cut"), ("next_due_date", "card_due")):
            when = date.fromisoformat(status[key])
            if not (start <= when <= end):
                continue
            out.append({
                "kind": kind, "date": when.isoformat(), "id": card["id"],
                "name": f"{card['name']}",
                "amount": status["pago_no_intereses"] if kind == "card_due"
                else {"amount": "0", "currency": card["currency"]},
                "status": "upcoming", "txn_id": None,
                "direction": "out" if kind == "card_due" else "none",
            })
    return out


def _loan_items(ws_id: str, start: date, end: date, skip_loan_ids: set[str]) -> list[dict]:
    try:
        from ..pf import credit
    except Exception:  # noqa: BLE001
        return []
    from . import cadence as cad

    out = []
    try:
        loans = credit.list_loans(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for loan in loans:
        if loan["id"] in skip_loan_ids:
            continue
        try:
            payment = Decimal(credit.loan_amortization(ws_id, loan["id"])["payment"])
        except Exception:  # noqa: BLE001
            continue
        loan_start = date.fromisoformat(loan["start"])
        for when in cad.occurrences_between(loan_start, "monthly", start, end, anchor_day=loan_start.day):
            out.append({
                "kind": "loan", "date": when.isoformat(), "id": loan["id"], "name": loan["name"],
                "amount": {"amount": str(q2(payment)), "currency": loan["currency"]},
                "status": "upcoming", "txn_id": None, "direction": "out",
            })
    return out


def _tax_items(ws_id: str, start: date, end: date) -> list[dict]:
    """Tax deadlines only for workspaces with the tax module on; simple mode sees none."""
    if not pf_bridge.module_on(ws_id, "tax"):
        return []
    try:
        from ..insights.router import api_calendar
    except Exception:  # noqa: BLE001
        return []
    try:
        rows = api_calendar(ws_id, start.isoformat(), end.isoformat())
    except Exception:  # noqa: BLE001
        return []
    out = []
    currency = pf_bridge.base_currency(ws_id)
    for row in rows:
        if not str(row.get("kind", "")).startswith(("mx_", "us_")):
            continue
        out.append({
            "kind": "tax", "date": row["date"], "id": row["kind"],
            "name": row.get("title") or row["kind"],
            "amount": {"amount": "0", "currency": currency},
            "status": "upcoming", "txn_id": None, "direction": "out",
        })
    return out


def calendar(ws_id: str, start: date, end: date, today: date | None = None,
             lang: str | None = None) -> dict:
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    raw = _commitment_items(ws_id, start, end, today)
    linked_loans = set(raw[-1]["_linked_loans"])
    items = raw[:-1]
    items += _card_items(ws_id, start, end)
    items += _loan_items(ws_id, start, end, linked_loans)
    items += _tax_items(ws_id, start, end)

    base = pf_bridge.base_currency(ws_id)
    by_day: dict[str, list[dict]] = {}
    for item in items:
        by_day.setdefault(item["date"], []).append(item)

    days = []
    for day in sorted(by_day):
        rows = sorted(by_day[day], key=lambda r: (r["kind"], r["name"]))
        total_out = sum(
            (Decimal(r["amount"]["amount"]) for r in rows
             if r["direction"] == "out" and r["status"] not in ("skipped",)),
            Decimal("0"),
        )
        total_in = sum(
            (Decimal(r["amount"]["amount"]) for r in rows if r["direction"] == "in"), Decimal("0")
        )
        currency = base
        days.append({
            "date": day,
            "items": [{k: v for k, v in r.items() if k != "direction"} for r in rows],
            "total_out": {"amount": str(q2(total_out)), "currency": currency},
            "total_in": {"amount": str(q2(total_in)), "currency": currency},
        })

    explain = Explain(summary=i18n_t("organizer.calendar", lang))
    explain.add_step("range", f"{start.isoformat()} … {end.isoformat()}")
    explain.add_step("days_with_items", len(days))
    explain.add_step("items", len(items))
    explain.add_step(
        "paid_match_rule",
        f"±{occ.DATE_WINDOW_DAYS} days and ±{occ.AMOUNT_TOLERANCE * 100:.0f}% of the expected amount",
    )
    return {"days": days, "explain": explain.model_dump()}
