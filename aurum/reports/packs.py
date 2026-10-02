"""Builds a :class:`aurum.reports.builder.Report` per pack.

Every pack composes other modules' *already-computed* endpoints in-process (the reports module never
computes a tax or PF figure itself). Every import is defensive — a workspace that has
no US profile, no cross-border profile, or no holdings simply gets a section saying so, never a 500.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ..core.i18n import t, ws_lang
from ..core.workspaces import Workspace, WorkspaceNotFound, get_workspace
from .builder import KPI, ExplainBlock, Report, Section, Table

PACKS = {
    "monthly-review": {
        "es": "Revisión mensual",
        "en": "Monthly review",
        "period_kind": "month",
        "applies": lambda ws: True,
    },
    "net-worth": {
        "es": "Patrimonio neto",
        "en": "Net worth",
        "period_kind": "none",
        "applies": lambda ws: True,
    },
    "mx-annual": {
        "es": "Anual MX (RESICO)",
        "en": "MX annual (RESICO)",
        "period_kind": "year",
        "applies": lambda ws: "MX" in ws.jurisdictions,
    },
    "us-organizer-bundle": {
        "es": "Paquete organizador US",
        "en": "US organizer bundle",
        "period_kind": "year",
        "applies": lambda ws: "US" in ws.jurisdictions,
    },
    "client-pack": {
        "es": "Paquete para cliente",
        "en": "Client pack",
        "period_kind": "period",
        "applies": lambda ws: ws.kind == "advisory",
    },
}


def catalog(ws_id: str) -> dict[str, Any]:
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound:
        return {"workspace": ws_id, "packs": [], "warnings": [f"workspace {ws_id} does not exist"]}
    packs = []
    for pack_id, meta in PACKS.items():
        applicable = bool(meta["applies"](ws))
        packs.append(
            {
                "pack": pack_id,
                "title": {"es": meta["es"], "en": meta["en"]},
                "applicable": applicable,
                "period_kind": meta["period_kind"],
                "url": f"/api/reports/{ws_id}/{pack_id}",
            }
        )
    return {"workspace": ws_id, "kind": ws.kind, "jurisdictions": ws.jurisdictions, "packs": packs}


def _money(a: dict[str, Any] | str | None) -> str:
    if not a:
        return "—"
    if isinstance(a, dict):
        return f"{a.get('amount', '0.00')} {a.get('currency', '')}".strip()
    return str(a)


def _month_bounds(period: str | None) -> tuple[str, list[str]]:
    """``period`` is ``YYYY-MM``; default to the current month."""
    p = period or date.today().strftime("%Y-%m")
    return p, [p]


def _year_months(year: int) -> list[str]:
    return [f"{year}-{m:02d}" for m in range(1, 13)]


# --------------------------------------------------------------------------- monthly-review


def monthly_review_report(ws_id: str, period: str | None, lang: str | None = None) -> Report:
    from ..pf import budgets as budgets_mod
    from ..pf import review as review_mod

    period, _ = _month_bounds(period)
    lang = lang or ws_lang(ws_id, lang)
    warnings: list[str] = []

    try:
        review = review_mod.monthly_review(ws_id, period, lang)
    except Exception as e:  # noqa: BLE001 — a data problem must not break the report
        return _error_report("monthly-review", ws_id, period, lang, str(e))

    sections: list[Section] = []
    overview = Section(
        title=t("reports.monthly_review.overview", lang),
        kpis=[
            KPI(label="Ingreso / Income", value=_money(review["income"])),
            KPI(label="Gasto / Expense", value=_money(review["expense"])),
            KPI(label="Neto / Net", value=_money(review["net"])),
            KPI(
                label="Delta ingreso vs. mes anterior / Income delta vs. prior month",
                value=str(review["vs_previous_month"]["income_delta"]),
            ),
            KPI(
                label="Delta gasto vs. mes anterior / Expense delta vs. prior month",
                value=str(review["vs_previous_month"]["expense_delta"]),
            ),
        ],
        explains=[ExplainBlock(summary=review["explain"]["summary"])],
    )
    sections.append(overview)

    if review["top_labels"]:
        sections.append(
            Section(
                title=t("reports.monthly_review.top_labels", lang),
                tables=[
                    Table(
                        title="",
                        columns=["Label", "Amount"],
                        rows=[[row["label"], row["amount"]] for row in review["top_labels"]],
                    )
                ],
            )
        )

    if review["anomalies"]:
        sections.append(
            Section(
                title=t("reports.monthly_review.anomalies", lang),
                tables=[
                    Table(
                        title="",
                        columns=["Label", "Amount", "Trailing avg.", "Ratio"],
                        rows=[
                            [a["label"], a["amount"], a["trailing_average"], a["ratio"]]
                            for a in review["anomalies"]
                        ],
                    )
                ],
                notes=[t("reports.monthly_review.anomalies_note", lang)],
            )
        )

    try:
        budget_rows = budgets_mod.budget_status(ws_id, period, lang).get("budgets", [])
        if budget_rows:
            sections.append(
                Section(
                    title=t("reports.monthly_review.budgets", lang),
                    tables=[
                        Table(
                            title="",
                            columns=["Label", "Budget", "Spent", "Alert"],
                            rows=[
                                [
                                    b.get("label_name") or b.get("label_id", ""),
                                    _money(b.get("budget")),
                                    _money(b.get("spent")),
                                    b.get("alert", ""),
                                ]
                                for b in budget_rows
                            ],
                        )
                    ],
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"budgets unavailable: {e}")

    if review["goals_progress"]:
        sections.append(
            Section(
                title=t("reports.monthly_review.goals", lang),
                tables=[
                    Table(
                        title="",
                        columns=["Goal", "Target", "Progress", "Monthly required"],
                        rows=[
                            [
                                g.get("name", g.get("id", "")),
                                f"{g.get('target', '')} {g.get('currency', '')}".strip(),
                                _money(g.get("progress")),
                                _money(g.get("monthly_required")),
                            ]
                            for g in review["goals_progress"]
                        ],
                    )
                ],
            )
        )

    if review["upcoming_bills"]:
        sections.append(
            Section(
                title=t("reports.monthly_review.upcoming_bills", lang),
                tables=[
                    Table(
                        title="",
                        columns=["Payee", "Amount", "Next expected date"],
                        rows=[
                            [b.get("payee", ""), _money(b.get("amount")), b.get("next_expected_date", "")]
                            for b in review["upcoming_bills"]
                        ],
                    )
                ],
            )
        )

    try:
        from ..pf import accounts as accounts_mod

        nw = accounts_mod.net_worth_as_of(ws_id)
        sections.append(
            Section(title=t("reports.monthly_review.net_worth", lang), kpis=[KPI(label="Net worth", value=str(nw))])
        )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"net worth unavailable: {e}")

    return Report(
        title=f"{PACKS['monthly-review'][lang if lang in ('es', 'en') else 'es']} — {period}",
        workspace=ws_id,
        period=period,
        lang=lang,
        rule_versions=review["explain"].get("rule_versions", []),
        sections=sections,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- mx-annual


def mx_annual_report(ws_id: str, year: int | None, lang: str | None = None) -> Report:
    from ..pf import labels as labels_mod
    from ..tax.month_close import month_close

    year = year or date.today().year
    lang = lang or ws_lang(ws_id, lang)
    ws = _safe_ws(ws_id)
    warnings: list[str] = []
    rule_versions: set[str] = set()

    month_rows: list[list[str]] = []
    isr_total = Decimal("0")
    iva_total = Decimal("0")
    isr_retained_total = Decimal("0")
    iva_retained_total = Decimal("0")
    diffs_total = 0
    months_ok = 0
    for period in _year_months(year):
        try:
            payload = month_close(ws_id, period, rfc=(ws.profile or {}).get("rfc") if ws else None, lang=lang)
        except Exception as e:  # noqa: BLE001 — likely no CFDIs for that month
            warnings.append(f"{period}: {e}")
            continue
        months_ok += 1
        isr = Decimal(payload["isr"]["value"]["amount"])
        iva = Decimal(payload["iva"]["payable"]["amount"])
        isr_total += isr
        iva_total += iva
        isr_retained_total += Decimal(payload["retentions"]["isr"]["amount"])
        iva_retained_total += Decimal(payload["retentions"]["iva"]["amount"])
        diffs_total += len(payload["diffs"])
        rule_versions.update(payload["isr"]["explain"].get("rule_versions", []))
        rule_versions.update(payload["iva"]["explain"].get("rule_versions", []))
        month_rows.append(
            [
                period,
                _money(payload["income"]["collected"]),
                _money(payload["isr"]["value"]),
                _money(payload["iva"]["payable"]),
                str(len(payload["diffs"])),
            ]
        )

    sections: list[Section] = [
        Section(
            title=t("reports.mx_annual.summary", lang, year=year),
            kpis=[
                KPI(label="Meses con datos / Months with data", value=f"{months_ok}/12"),
                KPI(label="ISR calculado (anual) / ISR computed (annual)", value=f"{isr_total} MXN"),
                KPI(label="IVA calculado (anual) / IVA computed (annual)", value=f"{iva_total} MXN"),
                KPI(label="ISR retenido / ISR withheld", value=f"{isr_retained_total} MXN"),
                KPI(label="IVA retenido / IVA withheld", value=f"{iva_retained_total} MXN"),
                KPI(label="Diferencias vs. prellenado / Prefill differences", value=str(diffs_total)),
            ],
            notes=[t("reports.mx_annual.summary_note", lang)],
        )
    ]
    if month_rows:
        sections.append(
            Section(
                title=t("reports.mx_annual.month_closes", lang),
                tables=[
                    Table(
                        title="",
                        columns=["Period", "Income collected", "ISR", "IVA payable", "Diffs"],
                        rows=month_rows,
                    )
                ],
            )
        )

    try:
        deduction_rows = _personal_deduction_candidates(ws_id, year, labels_mod)
        if deduction_rows:
            sections.append(
                Section(
                    title=t("reports.mx_annual.deduction_candidates", lang),
                    tables=[
                        Table(title="", columns=["Label", "Account", "Total paid"], rows=deduction_rows)
                    ],
                    notes=[t("reports.mx_annual.deduction_note", lang)],
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"personal deduction candidates unavailable: {e}")

    sections.append(
        Section(
            title=t("reports.mx_annual.for_accountant", lang),
            notes=[
                t("reports.mx_annual.note.confirm_ppd", lang),
                t("reports.mx_annual.note.review_deposits", lang),
                t("reports.mx_annual.note.gather_receipts", lang),
                t("reports.mx_annual.note.reconcile_withholding", lang),
            ],
        )
    )

    return Report(
        title=f"{PACKS['mx-annual'][lang if lang in ('es', 'en') else 'es']} {year}",
        workspace=ws_id,
        period=str(year),
        lang=lang,
        draft=True,
        rule_versions=sorted(rule_versions),
        sections=sections,
        warnings=warnings,
    )


def _personal_deduction_candidates(ws_id: str, year: int, labels_mod: Any) -> list[list[str]]:
    from ..ledger.base import get_ledger

    labels = [lbl for lbl in labels_mod.list_labels(ws_id) if lbl.get("tax", {}).get("MX", {}).get("personal_deduction")]
    if not labels:
        return []
    ledger = get_ledger()
    txns = ledger.journal(ws_id, start=date(year, 1, 1), end=date(year, 12, 31))
    totals: dict[str, Decimal] = {lbl["account"]: Decimal("0") for lbl in labels}
    for txn in txns:
        for p in txn.postings:
            if p.amount is not None and p.account in totals and p.amount.amount > 0:
                totals[p.account] += p.amount.amount
    rows = []
    for lbl in labels:
        total = totals.get(lbl["account"], Decimal("0"))
        if total > 0:
            rows.append([lbl["name"], lbl["account"], f"{total} MXN"])
    return rows


# --------------------------------------------------------------------------- us-organizer-bundle


def us_organizer_bundle_report(ws_id: str, year: int | None, lang: str | None = None) -> Report:
    from ..crossborder import assessment as xb_assess
    from ..crossborder import profile as xb_profile
    from ..taxus import service as taxus_service

    year = year or date.today().year
    lang = lang or ws_lang(ws_id, lang)
    warnings: list[str] = []
    rule_versions: set[str] = set()
    sections: list[Section] = []

    try:
        annual = taxus_service.annual(ws_id, year, lang=lang)
    except Exception as e:  # noqa: BLE001
        return _error_report("us-organizer-bundle", ws_id, str(year), lang, str(e))

    if not annual.get("applicable"):
        sections.append(Section(title=t("reports.us_organizer.schedule_c", lang), notes=[annual.get("reason", "not applicable")]))
        warnings.append(annual.get("reason", "not applicable"))
    else:
        sched = annual["schedule_c"]
        sections.append(
            Section(
                title=t("reports.us_organizer.schedule_c_summary", lang),
                kpis=[
                    KPI(label="Gross receipts", value=_money(sched["gross_receipts"])),
                    KPI(label="COGS", value=_money(sched["cost_of_goods_sold"])),
                    KPI(label="Expenses", value=_money(sched["expenses"])),
                    KPI(label="Net profit", value=_money(sched["net"])),
                ],
                explains=[ExplainBlock(summary=sched["explain"]["summary"])],
            )
        )
        sections.append(
            Section(
                title=t("reports.us_organizer.se_tax_estimates", lang),
                kpis=[
                    KPI(label="Self-employment tax", value=_money(annual["se_tax"]["value"])),
                    KPI(label="Income tax", value=_money(annual["income_tax"]["value"])),
                    KPI(label="Total tax (computed)", value=_money(annual["total_tax"])),
                    KPI(
                        label="Quarterly estimate (each, computed)",
                        value=_money(annual["quarterly"]["amount_each"]),
                    ),
                ],
                notes=[t("reports.us_organizer.se_tax_note", lang)],
                tables=[
                    Table(title=t("reports.us_organizer.due_dates", lang), columns=["Date"], rows=[[d] for d in annual["quarterly"]["due_dates"]])
                ],
            )
        )
        rule_versions.update(annual["schedule_c"]["explain"].get("rule_versions", []))
        rule_versions.update(annual["se_tax"]["explain"].get("rule_versions", []))
        rule_versions.update(annual["income_tax"]["explain"].get("rule_versions", []))
        warnings.extend(annual.get("warnings", []))

        try:
            tx = taxus_service.tx_franchise(ws_id, year, lang=lang)
            sections.append(
                Section(
                    title=t("reports.us_organizer.tx_franchise", lang),
                    kpis=[
                        KPI(label="No tax due", value=str(tx.get("no_tax_due"))),
                        KPI(label="Threshold", value=_money(tx.get("no_tax_due_threshold"))),
                    ],
                )
            )
        except Exception as e:  # noqa: BLE001
            warnings.append(f"tx franchise unavailable: {e}")

    try:
        _, xb = xb_profile.load(ws_id)
        if xb is not None:
            assessment = xb_assess.assess(ws_id, xb, lang=lang)
            sections.append(
                Section(
                    title=t("reports.us_organizer.crossborder", lang),
                    kpis=[
                        KPI(label="MX resident", value=str(assessment["residency"]["mx"])),
                        KPI(label="US resident", value=str(assessment["residency"]["us"])),
                        KPI(label="FBAR required", value=str(assessment["fbar"]["required"])),
                    ],
                    notes=assessment.get("flags", []),
                )
            )
            accounts = xb.foreign_accounts
            if accounts:
                sections.append(
                    Section(
                        title=t("reports.us_organizer.fbar_accounts", lang),
                        tables=[
                            Table(
                                title="",
                                columns=["Country", "Institution", "Max balance (USD)"],
                                rows=[
                                    [a.country, a.institution or "—", str(a.max_balance_usd)]
                                    for a in accounts
                                ],
                            )
                        ],
                        notes=[t("reports.us_organizer.fbar_note", lang)],
                    )
                )
        else:
            sections.append(
                Section(
                    title=t("reports.us_organizer.crossborder", lang),
                    notes=[t("reports.us_organizer.no_crossborder_profile", lang, ws_id=ws_id)],
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"cross-border assessment unavailable: {e}")

    sections.append(
        Section(
            title=t("reports.us_organizer.for_preparer", lang),
            notes=[
                t("reports.us_organizer.note.not_a_return", lang),
                t("reports.us_organizer.note.estimate_only", lang),
            ],
        )
    )

    return Report(
        title=f"{PACKS['us-organizer-bundle'][lang if lang in ('es', 'en') else 'es']} {year}",
        workspace=ws_id,
        period=str(year),
        lang=lang,
        draft=True,
        rule_versions=sorted(rule_versions),
        sections=sections,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- client-pack


def client_pack_report(ws_id: str, period: str | None, lang: str | None = None, reviewer: str | None = None) -> Report:
    from ..ledger.base import get_ledger
    from ..ledger.statements import build_statement

    period, _ = _month_bounds(period)
    lang = lang or ws_lang(ws_id, lang)
    ws = _safe_ws(ws_id)
    warnings: list[str] = []
    sections: list[Section] = []

    monthly = monthly_review_report(ws_id, period, lang)
    exec_summary = Section(title=t("reports.client_pack.exec_summary", lang))
    for s in monthly.sections:
        if s.kpis:
            exec_summary.kpis.extend(s.kpis[:3])
            break
    sections.append(exec_summary)

    try:
        ledger = get_ledger()
        currency = ws.base_currency if ws else "MXN"
        pnl = build_statement(ledger, ws_id, period, "pnl", currency, lang)
        sections.append(
            Section(
                title=t("reports.client_pack.statements_pnl", lang),
                kpis=[KPI(label="Net", value=_money(pnl["net"]))],
                tables=[
                    Table(
                        title=s["title"],
                        columns=["Account", "Amount"],
                        rows=[[r["account"], _money(r["amount"])] for r in s["rows"]],
                    )
                    for s in pnl["sections"]
                ],
            )
        )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"statements unavailable: {e}")

    try:
        if ws and "MX" in ws.jurisdictions:
            from ..tax.month_close import month_close

            tax_payload = month_close(ws_id, period, rfc=(ws.profile or {}).get("rfc"), lang=lang)
            sections.append(
                Section(
                    title=t("reports.client_pack.tax_position", lang),
                    kpis=[
                        KPI(label="ISR", value=_money(tax_payload["isr"]["value"])),
                        KPI(label="IVA payable", value=_money(tax_payload["iva"]["payable"])),
                    ],
                )
            )
        elif ws and "US" in ws.jurisdictions:
            from ..taxus import service as taxus_service

            annual = taxus_service.annual(ws_id, int(period[:4]), lang=lang)
            if annual.get("applicable"):
                sections.append(
                    Section(
                        title=t("reports.client_pack.tax_position", lang),
                        kpis=[
                            KPI(label="Net profit (Schedule C, YTD)", value=_money(annual["schedule_c"]["net"])),
                            KPI(label="Total tax (computed)", value=_money(annual["total_tax"])),
                        ],
                    )
                )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"tax position unavailable: {e}")

    sections.append(
        Section(
            title=t("reports.client_pack.open_items", lang),
            notes=(monthly.warnings or [t("reports.client_pack.no_open_items", lang)]),
        )
    )

    watermark = f"Prepared with Aurum — reviewed by {reviewer}" if reviewer else None
    return Report(
        title=f"{PACKS['client-pack'][lang if lang in ('es', 'en') else 'es']} — {period}",
        workspace=ws_id,
        period=period,
        lang=lang,
        watermark_text=watermark,
        rule_versions=monthly.rule_versions,
        sections=sections,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- net-worth


def net_worth_report(ws_id: str, lang: str | None = None) -> Report:
    from ..pf import accounts as accounts_mod

    lang = lang or ws_lang(ws_id, lang)
    warnings: list[str] = []
    sections: list[Section] = []

    try:
        acc = accounts_mod.get_accounts(ws_id, lang)
        sections.append(
            Section(
                title=t("reports.net_worth.title", lang),
                kpis=[KPI(label="Net worth", value=_money(acc["net_worth"]))],
                tables=[
                    Table(
                        title=t("reports.net_worth.series_12mo", lang),
                        columns=["Month", "Net worth"],
                        rows=[[row["month"], row["net_worth"]] for row in acc["net_worth_series"]],
                    )
                ],
                explains=[ExplainBlock(summary=acc["explain"]["summary"])],
            )
        )
        for group_name, rows in acc["groups"].items():
            if not rows:
                continue
            sections.append(
                Section(
                    title=group_name.replace("_", " ").title(),
                    tables=[
                        Table(
                            title="",
                            columns=["Account", "Balances"],
                            rows=[
                                [r["account"], ", ".join(f"{b['amount']} {b['currency']}" for b in r["balances"])]
                                for r in rows
                            ],
                        )
                    ],
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"accounts unavailable: {e}")

    try:
        from ..holdings import trades as holdings_trades

        positions = holdings_trades.positions(ws_id)
        pos_rows = positions.get("positions", [])
        if pos_rows:
            sections.append(
                Section(
                    title=t("reports.net_worth.holdings_positions", lang),
                    tables=[
                        Table(
                            title="",
                            columns=["Symbol", "Units", "Cost basis", "Market value", "Unrealized"],
                            rows=[
                                [
                                    p["symbol"],
                                    p["units"],
                                    _money(p.get("cost_basis")),
                                    _money(p.get("market_value")),
                                    _money(p.get("unrealized")) if p.get("unrealized") is not None else "—",
                                ]
                                for p in pos_rows
                            ],
                        )
                    ],
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.append(f"holdings unavailable: {e}")

    return Report(
        title=f"{PACKS['net-worth'][lang if lang in ('es', 'en') else 'es']}",
        workspace=ws_id,
        lang=lang,
        sections=sections,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- helpers


def _safe_ws(ws_id: str) -> Workspace | None:
    try:
        return get_workspace(ws_id)
    except WorkspaceNotFound:
        return None


def _error_report(pack: str, ws_id: str, period: str | None, lang: str, message: str) -> Report:
    return Report(
        title=PACKS.get(pack, {}).get(lang if lang in ("es", "en") else "es", pack),
        workspace=ws_id,
        period=period,
        lang=lang,
        sections=[Section(title=t("reports.error.title", lang), notes=[message])],
        warnings=[message],
    )


BUILDERS = {
    "monthly-review": lambda ws, period, lang, **kw: monthly_review_report(ws, period, lang),
    "mx-annual": lambda ws, period, lang, **kw: mx_annual_report(ws, int(period) if period else None, lang),
    "us-organizer-bundle": lambda ws, period, lang, **kw: us_organizer_bundle_report(
        ws, int(period) if period else None, lang
    ),
    "client-pack": lambda ws, period, lang, **kw: client_pack_report(ws, period, lang, reviewer=kw.get("reviewer")),
    "net-worth": lambda ws, period, lang, **kw: net_worth_report(ws, lang),
}


def build(pack: str, ws_id: str, period: str | None, lang: str | None = None, **kw: Any) -> Report:
    if pack not in BUILDERS:
        raise KeyError(pack)
    return BUILDERS[pack](ws_id, period, lang, **kw)
