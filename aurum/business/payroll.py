"""Payroll: employee register, monthly run, ledger posting.

A run computes, per employee and from rules only (math lives in code):

* **ISR retenido** — LISR art. 96 monthly tarifa, reusing the *verified* Anexo 8 RMF 2026 table already
  registered by :mod:`aurum.rules.mx.general`, less the subsidio para el empleo ``(verify)``.
* **IMSS worker retention** — LSS arts. 25, 106 II, 107, 147, 168 II b).
* **IMSS employer quotas** — ``mx.imss.employer_quotas`` (per-branch breakdown).
* **INFONAVIT** — ``mx.infonavit.employer``, 5%.
* **ISN Nuevo León** — ``mx.nl.isn``, on the run's taxable payroll base, once for the whole run.

Nothing here is a filing: the PDF is watermarked "NÓMINA — BORRADOR / DRAFT" and nothing is transmitted.
PII rule: ``name`` and ``rfc`` are masked in every response, log line and audit record; the unmasked
values stay in SQLite and in the draft PDF the user downloads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta

from ..core import audit as audit_mod
from ..core.db import connect
from ..core.explain import Explain
from ..core.i18n import t
from ..core.money import Amount, q2
from ..ledger.base import Posting, Transaction, get_ledger
from ..rules.mx import nl_constants_2026 as K
from ..rules.mx.nl import employee_imss_quotas
from ..rules.registry import load_rules, registry

CURRENCY = "MXN"
DEFAULT_DAYS = Decimal("30")


class EmployeeNotFound(KeyError):
    pass


class RunNotFound(KeyError):
    pass


# --------------------------------------------------------------------------- schema migrations
#
# ``schema.sql`` is applied with ``CREATE TABLE IF NOT EXISTS``, so a table created before this
# change never gets these columns. Add them idempotently, guarded by ``PRAGMA table_info``.

def _ensure_run_columns(conn) -> None:
    """Idempotent: cheap ``PRAGMA table_info`` check, ``ALTER TABLE`` only when a column is missing."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(business_payroll_runs)").fetchall()}
    if "superseded_by" not in cols:
        conn.execute("ALTER TABLE business_payroll_runs ADD COLUMN superseded_by TEXT")
    if "voided_at" not in cols:
        conn.execute("ALTER TABLE business_payroll_runs ADD COLUMN voided_at TEXT")
    conn.commit()


def mask_name(name: str) -> str:
    """``"Empleada Demo Uno"`` -> ``"E. U***"`` — enough to recognise a row, not enough to identify."""
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "***"
    first = parts[0][0] + "."
    if len(parts) == 1:
        return f"{first}***"
    last = parts[-1]
    return f"{first} {last[0]}***"


def mask_rfc(rfc: str | None) -> str | None:
    if not rfc:
        return None
    return "*" * max(len(rfc) - 4, 0) + rfc[-4:]


def period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    return start, start + relativedelta(months=1) - relativedelta(days=1)


def _dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, float):
        raise TypeError("money inputs must be Decimal/str/int, not float")
    return Decimal(str(value))


# --------------------------------------------------------------------------- employee register


def add_employee(
    ws_id: str,
    name: str,
    daily_salary: Any,
    sbc_daily: Any = None,
    rfc: str | None = None,
    curp: str | None = None,
    nss: str | None = None,
    state: str = "NL",
    currency: str = CURRENCY,
    hired_on: date | None = None,
    employee_id: str | None = None,
) -> dict[str, Any]:
    emp_id = employee_id or f"emp-{uuid.uuid4().hex[:10]}"
    daily = q2(_dec(daily_salary))
    sbc = q2(_dec(sbc_daily)) if sbc_daily not in (None, "") else daily
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO business_employees (id, ws_id, name, rfc, curp, nss, daily_salary, "
            "sbc_daily, state, currency, hired_on, active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?)",
            (
                emp_id,
                ws_id,
                name,
                rfc,
                curp,
                nss,
                str(daily),
                str(sbc),
                state,
                currency,
                hired_on.isoformat() if hired_on else None,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    audit_mod.record(
        ws_id,
        "business.employee.add",
        {"employee_id": emp_id, "name": mask_name(name), "rfc": mask_rfc(rfc), "state": state},
        {"daily_salary": str(daily), "sbc_daily": str(sbc)},
    )
    return public_employee(get_employee(ws_id, emp_id))


def get_employee(ws_id: str, employee_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM business_employees WHERE ws_id=? AND id=?", (ws_id, employee_id)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise EmployeeNotFound(employee_id)
    return dict(row)


def list_employees(ws_id: str, active_only: bool = True) -> list[dict[str, Any]]:
    conn = connect()
    try:
        sql = "SELECT * FROM business_employees WHERE ws_id=?"
        if active_only:
            sql += " AND active=1"
        rows = conn.execute(sql + " ORDER BY name", (ws_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def deactivate_employee(ws_id: str, employee_id: str) -> dict[str, Any]:
    get_employee(ws_id, employee_id)
    conn = connect()
    try:
        conn.execute("UPDATE business_employees SET active=0 WHERE ws_id=? AND id=?", (ws_id, employee_id))
        conn.commit()
    finally:
        conn.close()
    return public_employee(get_employee(ws_id, employee_id))


def public_employee(row: dict[str, Any]) -> dict[str, Any]:
    """The API/log-safe shape: name and RFC masked, amounts as Amount dicts."""
    currency = row.get("currency") or CURRENCY
    return {
        "id": row["id"],
        "name": mask_name(row["name"]),
        "rfc": mask_rfc(row.get("rfc")),
        "daily_salary": {"amount": str(row["daily_salary"]), "currency": currency},
        "sbc_daily": {"amount": str(row["sbc_daily"]), "currency": currency},
        "state": row.get("state") or "NL",
        "active": bool(row.get("active", 1)),
        "hired_on": row.get("hired_on"),
    }


# --------------------------------------------------------------------------- wage ISR (LISR art. 96)


def wage_isr(monthly_gross: Decimal, currency: str = CURRENCY) -> dict[str, Any]:
    """Monthly wage ISR retention: art. 96 tarifa, less the subsidio para el empleo ``(verify)``."""
    from ..rules.mx.general import CITATION_ART_96, ISR_TABLE_MONTHLY_2026, apply_table

    base = q2(monthly_gross)
    tax, rate, upper = apply_table(base, list(ISR_TABLE_MONTHLY_2026))
    subsidy = Decimal("0")
    subsidy_applied = False
    if base <= K.SUBSIDIO_EMPLEO_INCOME_CAP.value:
        subsidy = q2(min(K.SUBSIDIO_EMPLEO_MONTHLY.value, tax))
        subsidy_applied = True
    retention = q2(max(tax - subsidy, Decimal("0")))
    return {
        "gross": base,
        "tarifa_tax": q2(tax),
        "rate": rate,
        "bracket_upper": upper,
        "subsidy": subsidy,
        "subsidy_applied": subsidy_applied,
        "retention": retention,
        "citation": CITATION_ART_96,
        "verified_subsidy": K.SUBSIDIO_EMPLEO_MONTHLY.verified,
    }


# --------------------------------------------------------------------------- the run


def _void_ledger_txn(ws_id: str, txn_id: str | None) -> tuple[bool, str | None]:
    """Void a previously-posted payroll transaction. Returns ``(voided, reason_if_not)``.

    Reuses the ledger's existing void endpoint function (``aurum.ledger.router.void_transaction``)
    rather than reimplementing reversal/tagging here, so void semantics live in one place.
    """
    if not txn_id:
        return False, "no ledger transaction to void"
    from ..ledger.beancount_store import BeancountLedger

    store = get_ledger()
    if not isinstance(store, BeancountLedger):
        return False, "ledger store does not support voiding (in-memory fallback)"
    from fastapi import HTTPException

    from ..ledger.router import void_transaction

    try:
        void_transaction(ws_id, txn_id)
    except HTTPException as exc:
        if exc.status_code == 409:
            return True, None  # already voided — nothing more to do
        return False, f"void failed: {exc.detail}"
    return True, None


def _find_active_run(ws_id: str, period: str) -> dict[str, Any] | None:
    """The most recent non-superseded, non-voided run for ``(ws_id, period)``, or ``None``."""
    conn = connect()
    try:
        _ensure_run_columns(conn)
        row = conn.execute(
            "SELECT id FROM business_payroll_runs WHERE ws_id=? AND period=? AND superseded_by IS NULL "
            "AND voided_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (ws_id, period),
        ).fetchone()
    finally:
        conn.close()
    return get_run(ws_id, row["id"]) if row else None


def run_payroll(
    ws_id: str,
    period: str,
    days: Any = None,
    post: bool = True,
    lang: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Compute (and by default post) the payroll for ``period`` (``YYYY-MM``).

    Idempotent: a second call for the same ``(ws_id, period)`` returns the existing run
    (``already_ran: true``, the original ``txn_id``) instead of posting again. ``force=True`` voids
    the previous run's ledger transaction (when the ledger supports it) and posts a fresh one.
    """
    resolved_lang = lang or "es"
    load_rules()

    previous_txn_voided: bool | None = None
    previous_txn_void_reason: str | None = None
    superseded_run_id: str | None = None
    if post:
        existing = _find_active_run(ws_id, period)
        if existing and not force:
            return {**existing, "already_ran": True}
        if existing and force:
            superseded_run_id = existing["id"]
            previous_txn_voided, previous_txn_void_reason = _void_ledger_txn(ws_id, existing.get("txn_id"))

    start, end = period_bounds(period)
    n_days = _dec(days, str(DEFAULT_DAYS)) if days not in (None, "") else Decimal(str((end - start).days + 1))
    employees = list_employees(ws_id)
    imss_rule = registry.get("mx.imss.employer_quotas", on=end)
    infonavit_rule = registry.get("mx.infonavit.employer", on=end)
    isn_rule = registry.get("mx.nl.isn", on=end)

    currency = (employees[0].get("currency") if employees else None) or CURRENCY
    lines: list[dict[str, Any]] = []
    totals = {
        k: Decimal("0")
        for k in ("gross", "isr", "imss_employee", "imss_employer", "infonavit", "isn", "net", "employer_cost")
    }
    isn_base = Decimal("0")

    for emp in employees:
        daily = _dec(emp["daily_salary"])
        sbc = _dec(emp["sbc_daily"])
        gross = q2(daily * n_days)
        isr = wage_isr(gross, currency)
        emp_imss = employee_imss_quotas(sbc, n_days)
        emp_imss_total = q2(sum(emp_imss.values(), Decimal("0")))
        employer = imss_rule.breakdown(sbc_daily=str(sbc), days=str(n_days), currency=currency)
        employer_total = _dec(employer["total"]["amount"])
        infonavit = infonavit_rule.compute(sbc_daily=str(sbc), days=str(n_days), currency=currency)
        net = q2(gross - isr["retention"] - emp_imss_total)

        totals["gross"] += gross
        totals["isr"] += isr["retention"]
        totals["imss_employee"] += emp_imss_total
        totals["imss_employer"] += employer_total
        totals["infonavit"] += _dec(infonavit.value.amount)
        totals["net"] += net
        # Every employee here is a wage earner, so the whole cash wage is ISN base (art. 154); the
        # art. 160 exemptions (fondo de ahorro, despensa, …) are not part of this simple wage model.
        isn_base += gross

        lines.append(
            {
                "employee_id": emp["id"],
                "name": mask_name(emp["name"]),
                "rfc": mask_rfc(emp.get("rfc")),
                "state": emp.get("state") or "NL",
                "days": str(n_days),
                "gross": {"amount": str(gross), "currency": currency},
                "isr_retenido": {"amount": str(isr["retention"]), "currency": currency},
                "isr_tarifa": {"amount": str(isr["tarifa_tax"]), "currency": currency},
                "subsidio_empleo": {"amount": str(isr["subsidy"]), "currency": currency},
                "imss_employee": {"amount": str(emp_imss_total), "currency": currency},
                "imss_employee_detail": {k: str(v) for k, v in emp_imss.items()},
                "imss_employer": employer["total"],
                "imss_employer_branches": employer["branches"],
                "sbc_capped": employer["sbc_capped"],
                "infonavit": infonavit.value.model_dump(mode="json"),
                "net": {"amount": str(net), "currency": currency},
                "explain": _employee_explain(emp, gross, isr, emp_imss_total, employer, infonavit, n_days, currency, resolved_lang),
            }
        )

    isn = isn_rule.compute(payroll=str(q2(isn_base)), currency=currency)
    totals["isn"] = _dec(isn.value.amount)
    totals["employer_cost"] = q2(
        totals["gross"] + totals["imss_employer"] + totals["infonavit"] + totals["isn"]
    )
    for key in totals:
        totals[key] = q2(totals[key])

    explain = _run_explain(period, n_days, len(lines), totals, currency, isn, resolved_lang)
    run_id = f"pay-{period}-{uuid.uuid4().hex[:8]}"
    txn_id = _post_payroll(ws_id, period, end, totals, currency) if post and lines else None

    result = {
        "id": run_id,
        "workspace": ws_id,
        "period": period,
        "days": str(n_days),
        "currency": currency,
        "employees": len(lines),
        "lines": lines,
        "totals": {k: {"amount": str(v), "currency": currency} for k, v in totals.items()},
        "isn": {"value": isn.value.model_dump(mode="json"), "explain": isn.explain.model_dump(mode="json")},
        "txn_id": txn_id,
        "status": "draft",
        "warnings": _warnings(lines, lang),
        "explain": explain.model_dump(mode="json"),
        "already_ran": False,
    }
    if superseded_run_id:
        result["supersedes"] = superseded_run_id
        result["previous_txn_voided"] = previous_txn_voided
        if previous_txn_void_reason:
            result["previous_txn_void_reason"] = previous_txn_void_reason
    _store_run(ws_id, run_id, period, n_days, currency, totals, txn_id, result)
    if superseded_run_id:
        _mark_superseded(ws_id, superseded_run_id, run_id)
    audit_mod.record(
        ws_id,
        "business.payroll.run",
        {"period": period, "days": str(n_days), "employees": len(lines)},
        {k: str(v) for k, v in totals.items()},
        rule_versions=[
            f"{imss_rule.id}@{imss_rule.version}",
            f"{infonavit_rule.id}@{infonavit_rule.version}",
            f"{isn_rule.id}@{isn_rule.version}",
            "mx.general.isr_provisional@2026.1",
        ],
    )
    return result


def _employee_explain(
    emp: dict[str, Any],
    gross: Decimal,
    isr: dict[str, Any],
    emp_imss_total: Decimal,
    employer: dict[str, Any],
    infonavit: Any,
    n_days: Decimal,
    currency: str,
    lang: str = "es",
) -> dict[str, Any]:
    explain = Explain(
        summary=t(
            "business.payroll.employee.summary",
            lang,
            name=mask_name(emp["name"]),
            net=q2(gross - isr["retention"] - emp_imss_total),
            currency=currency,
            gross=gross,
            isr=isr["retention"],
            imss=emp_imss_total,
        ),
        rule_versions=[
            "mx.general.isr_provisional@2026.1",
            "mx.imss.employer_quotas@2026.1",
            "mx.infonavit.employer@2026.1",
        ],
        citations=[isr["citation"], K.INFONAVIT_EMPLOYER.citation, K.CV_EMPLOYER_TABLE_FINAL.citation],
    )
    explain.add_step(t("business.payroll.employee.step.daily_salary", lang), emp["daily_salary"])
    explain.add_step(t("business.payroll.employee.step.period_days", lang), n_days)
    explain.add_step(t("business.payroll.employee.step.gross", lang), gross, formula=f"{emp['daily_salary']} × {n_days}")
    explain.add_step(
        t("business.payroll.employee.step.isr_tarifa", lang),
        isr["tarifa_tax"],
        formula=t("business.payroll.employee.step.isr_tarifa_formula", lang, rate=isr["rate"]),
    )
    if isr["subsidy_applied"]:
        explain.add_step(
            t("business.payroll.employee.step.subsidy", lang),
            isr["subsidy"],
            formula=t("business.payroll.employee.step.subsidy_unverified", lang) if not isr["verified_subsidy"] else None,
        )
    explain.add_step(t("business.payroll.employee.step.isr_retained", lang), isr["retention"])
    explain.add_step(
        t("business.payroll.employee.step.imss_employee", lang),
        emp_imss_total,
        formula=t("business.payroll.employee.step.imss_employee_formula", lang),
    )
    explain.add_step(
        t("business.payroll.employee.step.sbc_daily", lang),
        emp["sbc_daily"],
        formula=t("business.payroll.employee.step.sbc_capped", lang) if employer["sbc_capped"] else None,
    )
    explain.add_step(t("business.payroll.employee.step.imss_employer", lang), employer["total"]["amount"])
    explain.add_step(
        t("business.payroll.employee.step.infonavit", lang),
        infonavit.value.amount,
        formula=t("business.payroll.employee.step.infonavit_formula", lang),
    )
    explain.add_step(t("business.payroll.employee.step.net", lang), q2(gross - isr["retention"] - emp_imss_total))
    return explain.model_dump(mode="json")


def _run_explain(
    period: str,
    n_days: Decimal,
    headcount: int,
    totals: dict[str, Decimal],
    currency: str,
    isn: Any,
    lang: str = "es",
) -> Explain:
    explain = Explain(
        summary=t(
            "business.payroll.run.summary",
            lang,
            period=period,
            employer_cost=q2(totals["employer_cost"]),
            currency=currency,
            headcount=headcount,
            gross=q2(totals["gross"]),
            imss_employer=q2(totals["imss_employer"]),
            infonavit=q2(totals["infonavit"]),
            isn=q2(totals["isn"]),
        ),
        rule_versions=[
            "mx.general.isr_provisional@2026.1",
            "mx.imss.employer_quotas@2026.1",
            "mx.infonavit.employer@2026.1",
            "mx.nl.isn@2026.1",
        ],
        citations=list(isn.explain.citations) + [K.INFONAVIT_EMPLOYER.citation, K.UMA_DAILY.citation],
    )
    explain.add_step(t("business.payroll.run.step.period_days", lang), n_days)
    explain.add_step(t("business.payroll.run.step.gross", lang), q2(totals["gross"]))
    explain.add_step(t("business.payroll.run.step.isr_retained", lang), q2(totals["isr"]))
    explain.add_step(t("business.payroll.run.step.imss_employee", lang), q2(totals["imss_employee"]))
    explain.add_step(
        t("business.payroll.run.step.net", lang), q2(totals["net"]), formula=t("business.payroll.run.step.net_formula", lang)
    )
    explain.add_step(t("business.payroll.run.step.imss_employer", lang), q2(totals["imss_employer"]))
    explain.add_step(t("business.payroll.run.step.infonavit", lang), q2(totals["infonavit"]))
    explain.add_step(
        t("business.payroll.run.step.isn", lang), q2(totals["isn"]), formula=t("business.payroll.run.step.isn_formula", lang)
    )
    explain.add_step(
        t("business.payroll.run.step.employer_cost", lang),
        q2(totals["employer_cost"]),
        formula=t("business.payroll.run.step.employer_cost_formula", lang),
    )
    return explain


def _warnings(lines: list[dict[str, Any]], lang: str | None) -> list[str]:
    out: list[str] = []
    if not K.SUBSIDIO_EMPLEO_MONTHLY.verified and any(
        Decimal(line["subsidio_empleo"]["amount"]) > 0 for line in lines
    ):
        out.append(
            "El subsidio para el empleo 2026 no está verificado contra el decreto (verify) — "
            "the 2026 employment subsidy was not read in a primary source."
        )
    if not K.CV_EMPLOYER_TABLE_2026.verified and lines:
        out.append(
            "La tabla gradual 2026 de cesantía y vejez no se leyó en fuente primaria (verify) — "
            "the 2026 cesantía-y-vejez employer column is published only as an image in the DOF."
        )
    if any(line["sbc_capped"] for line in lines):
        out.append("Al menos un SBC fue topado a 25 UMA (LSS art. 28).")
    out.append("Borrador. Aurum nunca transmite ni firma una declaración. / Draft, never transmitted.")
    return out


def _post_payroll(
    ws_id: str,
    period: str,
    when: date,
    totals: dict[str, Decimal],
    currency: str,
) -> str | None:
    """One accrual transaction per run: cost to Expenses:Payroll:*, obligations to Liabilities:Payroll:*."""

    def amt(value: Decimal) -> Amount:
        return Amount(amount=q2(value), currency=currency)

    postings = [
        Posting(account="Expenses:Payroll:Sueldos", amount=amt(totals["gross"])),
        Posting(account="Expenses:Payroll:IMSS-Patronal", amount=amt(totals["imss_employer"])),
        Posting(account="Expenses:Payroll:INFONAVIT", amount=amt(totals["infonavit"])),
        Posting(account="Expenses:Payroll:ISN", amount=amt(totals["isn"])),
        Posting(account="Liabilities:Payroll:Net", amount=amt(-totals["net"])),
        Posting(account="Liabilities:Payroll:ISR-Retenido", amount=amt(-totals["isr"])),
        Posting(account="Liabilities:Payroll:IMSS-Obrero", amount=amt(-totals["imss_employee"])),
        Posting(account="Liabilities:Payroll:IMSS-Patronal", amount=amt(-totals["imss_employer"])),
        Posting(account="Liabilities:Payroll:INFONAVIT", amount=amt(-totals["infonavit"])),
        Posting(account="Liabilities:Payroll:ISN", amount=amt(-totals["isn"])),
    ]
    postings = [p for p in postings if p.amount is not None and p.amount.amount != 0]
    if not postings:
        return None
    txn = Transaction(
        date=when,
        payee=None,
        narration=f"Nómina {period} (borrador)",
        postings=postings,
        tags=["payroll"],
        meta={"source": "business.payroll", "period": period},
    )
    return get_ledger().append(ws_id, txn)


def _store_run(
    ws_id: str,
    run_id: str,
    period: str,
    n_days: Decimal,
    currency: str,
    totals: dict[str, Decimal],
    txn_id: str | None,
    payload: dict[str, Any],
) -> None:
    import json

    conn = connect()
    try:
        _ensure_run_columns(conn)
        conn.execute(
            "INSERT OR REPLACE INTO business_payroll_runs (id, ws_id, period, days, currency, gross, net, "
            "isr_retenido, imss_employee, imss_employer, infonavit, isn, employer_cost, txn_id, detail_json, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                ws_id,
                period,
                str(n_days),
                currency,
                str(totals["gross"]),
                str(totals["net"]),
                str(totals["isr"]),
                str(totals["imss_employee"]),
                str(totals["imss_employer"]),
                str(totals["infonavit"]),
                str(totals["isn"]),
                str(totals["employer_cost"]),
                txn_id,
                json.dumps(payload, ensure_ascii=False, default=str),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_superseded(ws_id: str, run_id: str, superseded_by: str) -> None:
    conn = connect()
    try:
        _ensure_run_columns(conn)
        conn.execute(
            "UPDATE business_payroll_runs SET superseded_by=? WHERE ws_id=? AND id=?",
            (superseded_by, ws_id, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_runs(ws_id: str, period: str | None = None, include_superseded: bool = False) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _ensure_run_columns(conn)
        sql = (
            "SELECT id, period, days, currency, gross, net, isr_retenido, imss_employee, imss_employer, "
            "infonavit, isn, employer_cost, txn_id, superseded_by, voided_at, created_at "
            "FROM business_payroll_runs WHERE ws_id=?"
        )
        params: list[Any] = [ws_id]
        if period:
            sql += " AND period=?"
            params.append(period)
        if not include_superseded:
            sql += " AND superseded_by IS NULL"
        rows = conn.execute(sql + " ORDER BY created_at DESC", params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_run(ws_id: str, run_id: str) -> dict[str, Any] | None:
    import json

    conn = connect()
    try:
        _ensure_run_columns(conn)
        row = conn.execute(
            "SELECT detail_json, txn_id, superseded_by, voided_at FROM business_payroll_runs WHERE ws_id=? AND id=?",
            (ws_id, run_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    payload = json.loads(row["detail_json"])
    payload["id"] = payload.get("id", run_id)
    payload["superseded_by"] = row["superseded_by"]
    payload["voided_at"] = row["voided_at"]
    return payload


def delete_run(ws_id: str, run_id: str) -> dict[str, Any]:
    """Void a run's posting (if any) and mark it ``voided_at``, so a mistaken run can be undone."""
    run = get_run(ws_id, run_id)
    if run is None:
        raise RunNotFound(run_id)
    voided, reason = _void_ledger_txn(ws_id, run.get("txn_id"))
    conn = connect()
    try:
        _ensure_run_columns(conn)
        conn.execute(
            "UPDATE business_payroll_runs SET voided_at=? WHERE ws_id=? AND id=?",
            (datetime.now(UTC).isoformat(timespec="seconds"), ws_id, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    audit_mod.record(
        ws_id,
        "business.payroll.void",
        {"run_id": run_id, "period": run.get("period")},
        {"txn_voided": voided, "reason": reason},
    )
    result = {"id": run_id, "txn_voided": voided}
    if reason:
        result["reason"] = reason
    return result
