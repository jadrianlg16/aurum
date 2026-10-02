"""Business endpoints, mounted at ``/api/business``.

Nothing here files, stamps or sends anything: the payroll PDF is a watermarked draft, and
``POST /invoices/remind`` returns text for the user to send themselves.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..core.i18n import ws_lang
from ..rules.mx import nl_constants_2026 as K
from . import chart as chart_mod
from . import invoices as invoices_mod
from . import kpis as kpis_mod
from . import payroll as payroll_mod
from . import payroll_pdf

router = APIRouter(tags=["business"])


class EmployeeIn(BaseModel):
    name: str
    daily_salary: Decimal
    sbc_daily: Decimal | None = None
    rfc: str | None = None
    curp: str | None = None
    nss: str | None = None
    state: str = "NL"
    currency: str = "MXN"
    hired_on: date | None = None


class PayrollRunIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    days: Decimal | None = None
    post: bool = True
    lang: str | None = None
    force: bool = False


class TemplateIn(BaseModel):
    name: str = "mx_persona_moral"
    currency: str | None = None


class ReminderIn(BaseModel):
    uuid: str
    as_of: date | None = None
    client_name: str | None = None


# --------------------------------------------------------------------------- chart of accounts


@router.get("/templates")
def api_templates() -> dict:
    return {
        "templates": [
            {
                "name": name,
                "currency": currency,
                "accounts": chart_mod.template_accounts(name),
            }
            for name, currency in sorted(chart_mod.TEMPLATES.items())
        ]
    }


@router.post("/{ws}/chart")
def api_apply_template(ws: str, body: TemplateIn) -> dict:
    try:
        accounts = chart_mod.apply_business_template(ws, body.name, body.currency)
    except chart_mod.TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "workspace": ws,
        "template": body.name,
        "currency": body.currency or chart_mod.default_currency(body.name),
        "accounts": accounts,
        "count": len(accounts),
    }


# --------------------------------------------------------------------------- payroll


@router.get("/{ws}/payroll/employees")
def api_list_employees(ws: str, active_only: bool = True) -> list[dict]:
    return [payroll_mod.public_employee(r) for r in payroll_mod.list_employees(ws, active_only=active_only)]


@router.post("/{ws}/payroll/employees")
def api_add_employee(ws: str, body: EmployeeIn) -> dict:
    return payroll_mod.add_employee(
        ws,
        name=body.name,
        daily_salary=body.daily_salary,
        sbc_daily=body.sbc_daily,
        rfc=body.rfc,
        curp=body.curp,
        nss=body.nss,
        state=body.state,
        currency=body.currency,
        hired_on=body.hired_on,
    )


@router.delete("/{ws}/payroll/employees/{employee_id}")
def api_deactivate_employee(ws: str, employee_id: str) -> dict:
    try:
        return payroll_mod.deactivate_employee(ws, employee_id)
    except payroll_mod.EmployeeNotFound as exc:
        raise HTTPException(status_code=404, detail=f"unknown employee {employee_id}") from exc


@router.get("/{ws}/payroll")
def api_list_runs(ws: str, period: str | None = None, include_superseded: bool = False) -> list[dict]:
    return payroll_mod.list_runs(ws, period, include_superseded=include_superseded)


@router.post("/{ws}/payroll/run")
def api_run_payroll(ws: str, body: PayrollRunIn) -> dict:
    return payroll_mod.run_payroll(
        ws, body.period, days=body.days, post=body.post, lang=body.lang, force=body.force
    )


@router.delete("/{ws}/payroll/runs/{run_id}")
def api_delete_run(ws: str, run_id: str) -> dict:
    try:
        return payroll_mod.delete_run(ws, run_id)
    except payroll_mod.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=f"unknown payroll run {run_id}") from exc


@router.get("/{ws}/payroll/{run_id}")
def api_get_run(ws: str, run_id: str) -> dict:
    run = payroll_mod.get_run(ws, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown payroll run {run_id}")
    return run


@router.get("/{ws}/payroll/{run_id}/draft.pdf")
def api_run_pdf(ws: str, run_id: str) -> Response:
    run = payroll_mod.get_run(ws, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown payroll run {run_id}")
    pdf = payroll_pdf.render(run)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="nomina-{run["period"]}-borrador.pdf"'},
    )


# --------------------------------------------------------------------------- invoicing register


@router.get("/{ws}/invoices")
def api_invoices(
    ws: str,
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
    currency: str = "MXN",
    lang: str | None = None,
) -> dict:
    if period:
        start, end = kpis_mod.period_bounds(period)
    return invoices_mod.register(ws, start=start, end=end, as_of=as_of, currency=currency, lang=ws_lang(ws, lang))


@router.post("/{ws}/invoices/remind")
def api_invoice_reminder(ws: str, body: ReminderIn) -> dict:
    try:
        return invoices_mod.reminder(ws, body.uuid, as_of=body.as_of, client_name=body.client_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown invoice {body.uuid}") from exc


# --------------------------------------------------------------------------- KPIs and constants


@router.get("/{ws}/kpis")
def api_kpis(ws: str, period: str = Query(pattern=r"^\d{4}-\d{2}$"), currency: str | None = None, lang: str | None = None) -> dict:
    return kpis_mod.kpis(ws, period, currency=currency, lang=ws_lang(ws, lang))


@router.get("/constants/mx-nl")
def api_constants() -> dict:
    """Every NL/IMSS/INFONAVIT constant with its citation and whether it was read in a primary source."""
    return {"year": K.YEAR, "verified_on": K.VERIFIED_ON.isoformat(), "constants": K.table(), "unverified": K.unverified()}
