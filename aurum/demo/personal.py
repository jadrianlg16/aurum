"""``demo-personal``: a from-scratch personal workspace seeded entirely through the public pf/organizer
functions — never raw SQL, never a direct ledger append this module writes itself. It is the fixture
every "Mi dinero" screen can be demoed against without touching the tax-flavoured ``demo-mx``.

Feature-detection: the optional fields this seed uses (``EntryIn.commitment_id``, ``Goal.account_id``,
``CommitmentIn.account_id``) are checked in ``model_fields`` before use, so the seed still runs against
a model that lacks one of them.

Idempotent on ``workspace.json``'s ``profile.demo_seed.version``: once stamped, a second call is a no-op
that returns immediately — this is what lets ``--refresh`` run on every container boot.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from ..core.config import settings
from ..core.dates import add_months_keep_anchor, clamp_day, period_of, shift_period
from ..core.money import Amount
from ..core.workspaces import Workspace, WorkspaceNotFound, get_workspace, list_workspaces, save_workspace
from ..organizer.models import CommitmentIn
from ..pf import accounts_admin
from ..pf import budgets as pf_budgets
from ..pf import entries as pf_entries
from ..pf import goals as pf_goals
from ..pf import labels as pf_labels
from ..pf import streams as pf_streams

WS_ID = "demo-personal"
SEED_VERSION = 1


def _has_field(model_cls: type, name: str) -> bool:
    return name in getattr(model_cls, "model_fields", {})


def _label_id(ws_id: str, name: str) -> str | None:
    for lbl in pf_labels.list_labels(ws_id):
        if lbl["name"] == name:
            return lbl["id"]
    return None


def _stamp_seeded(ws_id: str, today: date) -> None:
    ws = get_workspace(ws_id)
    data = ws.model_dump()
    data["profile"] = {
        **data.get("profile", {}),
        "demo": True,
        "demo_seed": {"today": today.isoformat(), "version": SEED_VERSION},
    }
    save_workspace(Workspace(**data))


def _seed_entries(
    ws_id: str, today: date, checking: dict, card: dict, savings: dict, commitments: dict[str, Any]
) -> int:
    label_super = _label_id(ws_id, "Súper")
    label_comida = _label_id(ws_id, "Comida fuera")
    label_uber = _label_id(ws_id, "Uber/Taxi")
    label_gas = _label_id(ws_id, "Transporte/Gasolina")
    label_tel = _label_id(ws_id, "Internet/Teléfono")
    label_ent = _label_id(ws_id, "Entretenimiento")
    label_rent = _label_id(ws_id, "Renta/Hipoteca")
    label_income = _label_id(ws_id, "Ingreso freelance")
    has_commitment_field = _has_field(pf_entries.EntryIn, "commitment_id")

    created = 0
    this_month_start = today.replace(day=1)
    # The newest Netflix charge that is not in the future carries the commitment link, so the demo
    # shows a paid fixed payment on any day of the month (before the 15th that is last month's).
    netflix_days = [
        clamp_day(m.year, m.month, 15)
        for m in (add_months_keep_anchor(this_month_start, -back, 1) for back in (2, 1, 0))
    ]
    linked_netflix = max(d for d in netflix_days if d <= today)
    for months_back in (2, 1, 0):
        month_anchor = add_months_keep_anchor(this_month_start, -months_back, 1)
        year, month = month_anchor.year, month_anchor.month

        def d(day: int, _y=year, _m=month) -> date:
            return clamp_day(_y, _m, day)

        plan: list[tuple[str, date, str, dict, str | None, str]] = [
            ("expense", d(1), "9500.00", checking, label_rent, "Renta"),
            ("expense", d(3), "650.00", checking, label_super, "Súper"),
            ("expense", d(10), "700.00", checking, label_super, "Súper"),
            ("expense", d(17), "680.00", checking, label_super, "Súper"),
            ("expense", d(24), "720.00", checking, label_super, "Súper"),
            ("expense", d(12), "380.00", card, label_comida, "Comida fuera"),
            ("expense", d(26), "410.00", card, label_comida, "Comida fuera"),
            ("expense", d(8), "120.00", card, label_uber, "Uber"),
            ("expense", d(22), "145.00", card, label_uber, "Uber"),
            ("expense", d(18), "900.00", checking, label_gas, "Gasolina"),
            ("expense", d(20), "399.00", checking, label_tel, "Telcel"),
            ("expense", d(5), "649.00", checking, label_ent, "Gym"),
            ("expense", d(15), "219.00", checking, label_ent, "Netflix"),
            ("income", d(15), "22500.00", checking, label_income, "Sueldo"),
            ("income", d(30), "22500.00", checking, label_income, "Sueldo"),
            ("transfer", d(28), "1500.00", checking, None, "Ahorro viaje"),
        ]
        for kind, when, amount, acct, label_id, payee in plan:
            if when > today:
                continue  # future dates skipped
            kwargs: dict[str, Any] = {
                "kind": kind, "date": when, "amount": Amount(amount=amount), "account_id": acct["id"],
                "payee": payee, "source": "manual",
            }
            if kind == "transfer":
                kwargs["to_account_id"] = savings["id"]
            else:
                kwargs["label_id"] = label_id
            if payee == "Netflix" and when == linked_netflix:
                if has_commitment_field:
                    kwargs["commitment_id"] = commitments["Netflix"].id
                else:
                    kwargs["tags"] = ["pago-fijo"]
            pf_entries.create_entry(ws_id, pf_entries.EntryIn(**kwargs))
            created += 1
    return created


def seed_demo_personal(ws_id: str = WS_ID, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    try:
        ws = get_workspace(ws_id)
        if ws.profile.get("demo_seed", {}).get("version") == SEED_VERSION:
            return {"workspace": ws_id, "status": "already-seeded"}
    except WorkspaceNotFound:
        save_workspace(
            Workspace(
                id=ws_id, name="Demo personal", kind="personal", jurisdictions=["MX"], base_currency="MXN",
                language="es",
                profile={"demo": True, "demo_seed": {"today": today.isoformat(), "version": SEED_VERSION}},
            )
        )

    pf_labels.seed_defaults(ws_id)

    checking = accounts_admin.create_account(
        ws_id,
        accounts_admin.AccountIn(
            name="BBVA Nómina", type="checking", institution="BBVA",
            opening_balance=Amount(amount="18500.00"), opening_date=today,
        ),
        today=today,
    )
    accounts_admin.create_account(
        ws_id,
        accounts_admin.AccountIn(name="Efectivo", type="cash", opening_balance=Amount(amount="1200.00"), opening_date=today),
        today=today,
    )
    savings = accounts_admin.create_account(
        ws_id,
        accounts_admin.AccountIn(
            name="Ahorro viaje", type="savings", opening_balance=Amount(amount="12000.00"),
            opening_date=today - timedelta(days=95),
        ),
        today=today,
    )
    # No opening balance on the card: its debt is built entirely from the card entries below, so the
    # sign is right whether or not the liability-sign migration has run on this install.
    card = accounts_admin.create_account(
        ws_id,
        accounts_admin.AccountIn(
            name="Nu", type="credit_card", cut_day=15, due_day=5, credit_limit=Amount(amount="30000.00"),
        ),
        today=today,
    )

    pf_streams.create_stream(
        ws_id,
        pf_streams.IncomeStreamIn(
            name="Sueldo", source_type="salary", amount=Amount(amount="22500.00"),
            cadence="semimonthly", anchor_days=[15, 30], account_id=checking["id"],
        ),
        today=today,
    )

    from ..organizer import commitments as org_commitments

    commitment_specs = [
        ("rent", "Renta", "9500.00", 1, "needs"),
        ("subscription", "Netflix", "219.00", 15, "wants"),
        ("utility", "Telcel", "399.00", 20, "needs"),
        ("subscription", "Gym", "649.00", 3, "wants"),
    ]
    commitments: dict[str, Any] = {}
    for kind, name, amount, anchor_day, essential in commitment_specs:
        kwargs: dict[str, Any] = {
            "kind": kind, "name": name, "amount": Amount(amount=amount), "cadence": "monthly",
            "anchor_day": anchor_day, "essential": essential, "source": "manual",
        }
        if _has_field(CommitmentIn, "account_id"):
            kwargs["account_id"] = checking["id"]
        else:
            kwargs["account"] = checking["account"]
        commitments[name] = org_commitments.create(ws_id, CommitmentIn(**kwargs), today)

    period = period_of(today)
    prev_period = shift_period(period, -1)
    budget_specs = [("Súper", "4000"), ("Comida fuera", "2500"), ("Transporte/Gasolina", "1800")]
    budgets_created = 0
    for period_key in (prev_period, period):
        for name, amount in budget_specs:
            label_id = _label_id(ws_id, name)
            if label_id is None:
                continue
            pf_budgets.create_budget(
                ws_id, pf_budgets.Budget(label_id=label_id, period=period_key, amount=amount, rollover=False)
            )
            budgets_created += 1

    goal_kwargs: dict[str, Any] = {
        "kind": "purchase", "name": "Viaje a Japón", "target": "60000",
        "target_date": (today + timedelta(days=300)).isoformat(),
    }
    if _has_field(pf_goals.Goal, "account_id"):
        goal_kwargs["account_id"] = savings["id"]
    else:
        goal_kwargs["account"] = savings["account"]
    pf_goals.create_goal(ws_id, pf_goals.Goal(**goal_kwargs))

    entries_created = _seed_entries(ws_id, today, checking, card, savings, commitments)

    _stamp_seeded(ws_id, today)

    return {
        "workspace": ws_id,
        "accounts": 4,
        "streams": 1,
        "commitments": len(commitments),
        "budgets": budgets_created,
        "goals": 1,
        "entries": entries_created,
    }


def reanchor_demo_trials(ws_id: str = "demo-mx", today: date | None = None) -> list[str]:
    """The organizer demo seeds a live trial (``trial_ends = today + 5``) so the alerts have something
    to show; on an install older than a week it has already expired. Re-anchor expired trials of the
    demo workspace to ``today + 5`` on every ``--refresh`` (demo data only — never a real workspace)."""
    from ..organizer import commitments as org_commitments
    from ..organizer.models import CommitmentPatch

    today = today or date.today()
    try:
        ws = get_workspace(ws_id)
    except (WorkspaceNotFound, ValueError):
        return []
    if not ws.profile.get("demo"):
        return []
    moved: list[str] = []
    for c in org_commitments.list_commitments(ws_id):
        # an expired trial may already have been rolled forward to "active" by the organizer; the
        # row still carries its trial_ends, which is the tell
        if c.status in ("trial", "active") and c.trial_ends is not None and c.trial_ends < today:
            org_commitments.update_partial(
                ws_id, c.id, CommitmentPatch(status="trial", trial_ends=today + timedelta(days=5)), today=today
            )
            moved.append(c.id)
    return moved


def stamp_demos() -> list[str]:
    """``profile.demo=true`` on every ``demo-*`` workspace lacking it — ``demo-biz`` ships ``synthetic``
    (a persona-moral business fixture, deliberately not counted as a personal demo) and is skipped.
    ``demo-mx`` (the RESICO demo) also gets ``modules.tax`` on, so installs seeded before the flag
    existed keep their tax nudges."""
    stamped: list[str] = []
    for ws in list_workspaces():
        if not ws.id.startswith("demo-") or ws.id == "demo-biz":
            continue
        needs_demo = not ws.profile.get("demo")
        needs_tax = ws.id == "demo-mx" and not ws.modules.tax
        if not (needs_demo or needs_tax):
            continue
        data = ws.model_dump()
        if needs_demo:
            data["profile"] = {**data.get("profile", {}), "demo": True}
        if needs_tax:
            data["modules"] = {**data.get("modules", {}), "tax": True}
        save_workspace(Workspace(**data))
        stamped.append(ws.id)
    return stamped


def seed_demo_organizer(ws_id: str = "demo-mx") -> dict[str, Any]:
    """The organizer half of the ``demo-mx`` seed (here rather than inline in ``docker/entrypoint.sh``):
    recurring bank lines + commitments, then auto-accept the
    high-confidence detector candidates so the hub is populated on first open."""
    from ..organizer import detect as org_detect
    from ..organizer.demo_org import seed_demo_org

    report: dict[str, Any] = {"seed": seed_demo_org(ws_id), "accepted": 0}
    res = org_detect.detect(ws_id)
    candidates = res.get("candidates", res) if isinstance(res, dict) else res
    for cand in candidates:
        conf = cand.get("confidence", 0) if isinstance(cand, dict) else getattr(cand, "confidence", 0)
        cid = cand.get("id") if isinstance(cand, dict) else getattr(cand, "id", None)
        if cid and conf >= 0.8:
            try:
                org_detect.accept(ws_id, cid)
                report["accepted"] += 1
            except Exception as e:  # noqa: BLE001 — best-effort demo seed, never fails the boot
                report.setdefault("errors", []).append(str(e)[:120])
    marker = settings().workspace_dir(ws_id) / "docs" / "demo-org.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(report, default=str), encoding="utf-8")
    return report
