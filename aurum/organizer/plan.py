"""Envelope spending plan: Needs / Wants / Savings / Debt, planned vs. actual.

Planned amounts live in ``pf_budgets`` and are written **only** through ``aurum.pf.budgets`` public
functions — this module never touches the pf tables directly. A label's group comes from the
commitment attached to it when there is one (``Commitment.essential``), else from the account prefix
map below, which is stated in ``docs/modules/organizer.md`` so the classification is auditable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from . import commitments as cmt
from . import pf_bridge

GROUPS = ("needs", "wants", "savings", "debt")

# account prefix -> envelope group. Longest prefix wins.
ACCOUNT_GROUPS: list[tuple[str, str]] = [
    ("Assets:Investments", "savings"),
    ("Assets:Transfers", "savings"),
    ("Liabilities:", "debt"),
    ("Expenses:Housing", "needs"),
    ("Expenses:Food:Groceries", "needs"),
    ("Expenses:Health", "needs"),
    ("Expenses:Insurance", "needs"),
    ("Expenses:Education", "needs"),
    ("Expenses:Taxes", "needs"),
    ("Expenses:Transport", "needs"),
    ("Expenses:Fees", "needs"),
    ("Expenses:Work", "needs"),
    ("Income:", "savings"),
]


def group_for_account(account: str) -> str:
    best = ("", "wants")
    for prefix, group in ACCOUNT_GROUPS:
        if account.startswith(prefix) and len(prefix) > len(best[0]):
            best = (prefix, group)
    return best[1]


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    return start, start + relativedelta(months=1) - relativedelta(days=1)


def _labels(ws_id: str) -> list[dict]:
    try:
        from ..pf import labels as pf_labels

        return pf_labels.list_labels(ws_id)
    except Exception:  # noqa: BLE001
        return []


def _budgets(ws_id: str, period: str) -> list[dict]:
    try:
        from ..pf import budgets as pf_budgets

        return pf_budgets.list_budgets(ws_id, period)
    except Exception:  # noqa: BLE001
        return []


def _journal(ws_id: str, start: date, end: date, txns: list | None = None):
    """Live (void-aware) transactions in the period — through ``pf_bridge.live_txns``."""
    if txns is not None:
        return [t for t in txns if start <= t.date <= end]
    return pf_bridge.live_txns(ws_id, start, end)


def spent_by_account(ws_id: str, start: date, end: date, txns: list | None = None) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for txn in _journal(ws_id, start, end, txns):
        for p in txn.postings:
            if p.amount is None or not p.account.startswith("Expenses:"):
                continue
            if p.amount.amount <= 0:
                continue
            out[p.account] = out.get(p.account, Decimal("0")) + p.amount.amount
    return out


def income_actual(ws_id: str, start: date, end: date, txns: list | None = None) -> Decimal:
    total = Decimal("0")
    for txn in _journal(ws_id, start, end, txns):
        for p in txn.postings:
            if p.amount is not None and p.account.startswith("Income:") and p.amount.amount < 0:
                total += -p.amount.amount
    return q2(total)


def uncategorized(ws_id: str, start: date, end: date, txns: list | None = None) -> list[dict]:
    """Ledger movements that landed in a catch-all account and still need a label."""
    catch_all = ("Expenses:Other", "Expenses:Uncategorized")
    out = []
    for txn in _journal(ws_id, start, end, txns):
        for p in txn.postings:
            if p.amount is None or not p.account.startswith(catch_all) or p.amount.amount <= 0:
                continue
            out.append({
                "txn_id": (txn.links or [""])[0],
                "date": txn.date.isoformat(),
                "payee": txn.payee or txn.narration or "",
                "account": p.account,
                "amount": {"amount": str(q2(p.amount.amount)), "currency": p.amount.currency},
            })
    return out


def build_plan(ws_id: str, period: str | None = None, today: date | None = None,
               lang: str | None = None) -> dict:
    """Needs / Wants / Savings / Debt for ``period``. A commitment whose payments land in an account a
    budget already covers is **nested** under that budget row (``row["commitments"]``) instead of
    becoming a second row, so the group's ``actual`` counts the money once."""
    today = today or date.today()
    period = period or today.strftime("%Y-%m")
    lang = lang or ws_lang(ws_id)
    start, end = _period_bounds(period)
    currency = pf_bridge.base_currency(ws_id)

    labels = {lbl["id"]: lbl for lbl in _labels(ws_id)}
    commitments = [c for c in cmt.list_commitments(ws_id) if c.status in ("active", "trial")]
    group_by_label = {c.label_id: c.essential for c in commitments if c.label_id}
    txns = pf_bridge.live_txns(ws_id, start - relativedelta(days=3), end + relativedelta(days=3))
    spent = spent_by_account(ws_id, start, end, txns)

    grouped: dict[str, list[dict]] = {g: [] for g in GROUPS}
    budget_rows: list[dict] = []
    for budget in _budgets(ws_id, period):
        label = labels.get(budget["label_id"], {})
        account = label.get("account", "Expenses:Other")
        group = group_by_label.get(budget["label_id"]) or group_for_account(account)
        planned = Decimal(budget["amount"])
        actual = q2(spent.get(account, Decimal("0")))
        row = {
            "label_id": budget["label_id"],
            "commitment_id": None,
            "name": label.get("name", budget["label_id"]),
            "account": account,
            "planned": {"amount": str(q2(planned)), "currency": budget["currency"]},
            "actual": {"amount": str(actual), "currency": budget["currency"]},
            "left": {"amount": str(q2(planned - actual)), "currency": budget["currency"]},
            "pct": str((actual / planned).quantize(Decimal("0.0001"))) if planned else "0",
            "commitments": [],
        }
        grouped[group].append(row)
        budget_rows.append(row)

    for c in commitments:
        if c.kind == "income":
            continue
        planned = cmt.monthly_equivalent(c)
        paid, hit_account = _commitment_actual(ws_id, c, start, end, txns=txns)
        if hit_account is None and c.label_id and c.label_id in labels:
            hit_account = labels[c.label_id].get("account")
        host = _covering_budget(budget_rows, hit_account)
        if host is not None:
            host["commitments"].append({
                "id": c.id, "name": c.name,
                "planned": {"amount": str(planned), "currency": c.amount.currency},
            })
            continue
        grouped[c.essential].append({
            "label_id": c.label_id,
            "commitment_id": c.id,
            "name": c.name,
            "account": c.account,
            "planned": {"amount": str(planned), "currency": c.amount.currency},
            "actual": {"amount": str(paid), "currency": c.amount.currency},
            "left": {"amount": str(q2(planned - paid)), "currency": c.amount.currency},
            "pct": str((paid / planned).quantize(Decimal("0.0001"))) if planned else "0",
            "commitments": [],
        })

    groups = []
    for name in GROUPS:
        items = sorted(grouped[name], key=lambda i: i["name"])
        planned = q2(sum((Decimal(i["planned"]["amount"]) for i in items), Decimal("0")))
        actual = q2(sum((Decimal(i["actual"]["amount"]) for i in items), Decimal("0")))
        groups.append({
            "group": name,
            "planned": {"amount": str(planned), "currency": currency},
            "actual": {"amount": str(actual), "currency": currency},
            "left": {"amount": str(q2(planned - actual)), "currency": currency},
            "items": items,
        })

    expected = q2(sum(
        (cmt.monthly_equivalent(c) for c in commitments if c.kind == "income"), Decimal("0")
    ))
    actual_income = income_actual(ws_id, start, end, txns)
    total_actual = q2(sum((Decimal(g["actual"]["amount"]) for g in groups), Decimal("0")))
    expenses_actual = q2(sum((v for a, v in spent.items() if a.startswith("Expenses:")), Decimal("0")))
    savings_rate = (
        ((actual_income - expenses_actual) / actual_income).quantize(Decimal("0.0001"))
        if actual_income > 0 else Decimal("0")
    )

    explain = Explain(summary=i18n_t("organizer.plan", lang))
    explain.add_step("period", period)
    explain.add_step("income_expected", expected, formula=i18n_t("organizer.step.income_expected", lang))
    explain.add_step("income_actual", actual_income, formula=i18n_t("organizer.step.income_actual", lang))
    explain.add_step("total_actual", total_actual, formula=i18n_t("organizer.step.total_actual", lang))
    explain.add_step("expenses_actual", expenses_actual, formula=i18n_t("organizer.step.expenses_actual", lang))
    explain.add_step("savings_rate", savings_rate, formula=i18n_t("organizer.step.savings_rate", lang))
    return {
        "period": period,
        "currency": currency,
        "groups": groups,
        "income_expected": {"amount": str(expected), "currency": currency},
        "income_actual": {"amount": str(actual_income), "currency": currency},
        "expenses_actual": {"amount": str(expenses_actual), "currency": currency},
        "savings_rate": str(savings_rate),
        "uncategorized": uncategorized(ws_id, start, end, txns),
        "explain": explain.model_dump(),
    }


def _covering_budget(rows: list[dict], account: str | None) -> dict | None:
    """The budget row whose account covers ``account`` (prefix match, longest wins)."""
    if not account:
        return None
    best: dict | None = None
    for row in rows:
        acct = row["account"]
        if account == acct or account.startswith(acct + ":"):
            if best is None or len(acct) > len(best["account"]):
                best = row
    return best


def _commitment_actual(ws_id: str, c, start: date, end: date,
                       txns: list | None = None) -> tuple[Decimal, str | None]:
    """(paid this period, the Expenses/Liabilities account its matched payments posted to)."""
    from . import occurrences as occ

    by_link = {}
    for txn in txns or []:
        for link in txn.links or []:
            by_link[link] = txn
    total = Decimal("0")
    hit_account: str | None = None
    for o in occ.build(ws_id, c, start, end, today=end, txns=txns):
        if o.status != "paid":
            continue
        total += q2(o.amount.amount)
        txn = by_link.get(o.txn_id) if o.txn_id else None
        if txn is not None and hit_account is None:
            for p in txn.postings:
                if p.amount is not None and p.amount.amount > 0 and p.account.startswith(("Expenses:", "Liabilities:")):
                    hit_account = p.account
                    break
    return q2(total), hit_account


# --------------------------------------------------------------------------- auto plan


def auto_plan(ws_id: str, months: int = 3, period: str | None = None, today: date | None = None,
              lang: str | None = None) -> dict:
    """Write ``pf_budgets`` for ``period`` from the last ``months`` of spending, floored at commitments."""
    from ..pf import budgets as pf_budgets

    today = today or date.today()
    period = period or today.strftime("%Y-%m")
    lang = lang or ws_lang(ws_id)
    currency = pf_bridge.base_currency(ws_id)
    labels = _labels(ws_id)
    by_account = {lbl["account"]: lbl for lbl in labels}

    first_of_period, _ = _period_bounds(period)
    window_start = first_of_period - relativedelta(months=months)
    window_end = first_of_period - relativedelta(days=1)
    spent = spent_by_account(ws_id, window_start, window_end)

    floors: dict[str, Decimal] = {}
    for c in cmt.list_commitments(ws_id):
        if c.status not in ("active", "trial") or c.kind == "income" or not c.label_id:
            continue
        floors[c.label_id] = floors.get(c.label_id, Decimal("0")) + cmt.monthly_equivalent(c)

    existing = {b["label_id"]: b for b in _budgets(ws_id, period)}
    written = []
    explain = Explain(summary=i18n_t("organizer.plan.auto", lang, months=months))
    explain.add_step("window", f"{window_start.isoformat()} … {window_end.isoformat()}")
    for account, total in sorted(spent.items()):
        label = by_account.get(account)
        if label is None:
            continue
        average = q2(total / Decimal(months))
        planned = max(average, floors.get(label["id"], Decimal("0")))
        body = pf_budgets.Budget(
            label_id=label["id"], period=period, amount=str(planned), currency=currency, rollover=False
        )
        if label["id"] in existing:
            pf_budgets.update_budget(ws_id, existing[label["id"]]["id"], body)
        else:
            pf_budgets.create_budget(ws_id, body)
        explain.add_step(
            label["name"], planned,
            formula=f"max(avg {average} = {q2(total)}/{months}, commitments {floors.get(label['id'], 0)})",
        )
        written.append({
            "label_id": label["id"], "name": label["name"],
            "planned": {"amount": str(planned), "currency": currency},
            "average": {"amount": str(average), "currency": currency},
            "group": group_for_account(account),
        })
    explain.add_step("budgets_written", len(written))
    return {"period": period, "months": months, "written": written, "explain": explain.model_dump()}


def put_plan(ws_id: str, items: list[dict], period: str | None = None,
             today: date | None = None) -> dict:
    from ..pf import budgets as pf_budgets

    today = today or date.today()
    period = period or today.strftime("%Y-%m")
    currency = pf_bridge.base_currency(ws_id)
    existing = {b["label_id"]: b for b in _budgets(ws_id, period)}
    updated = []
    for item in items:
        label_id = item["label_id"]
        planned = str(q2(Decimal(str(item["planned"]))))
        body = pf_budgets.Budget(label_id=label_id, period=period, amount=planned, currency=currency)
        if label_id in existing:
            pf_budgets.update_budget(ws_id, existing[label_id]["id"], body)
        else:
            pf_budgets.create_budget(ws_id, body)
        updated.append({"label_id": label_id, "planned": {"amount": planned, "currency": currency}})
    return {"period": period, "updated": updated}
