"""Minimal ES/EN localization for ``Explain.summary`` text.

Only prose is localized here — never numbers, citations, rule ids, or response shapes. Callers
resolve the language once (``Workspace.language``, or an explicit ``?lang=`` query override that
wins when present) and pass it down to ``t()``.

Usage::

    from ..core.i18n import t
    summary = t("pf.net_worth", lang)
    summary = t("pf.budget_status", lang, name=label_name)
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["es", "en"]

_DEFAULT: Lang = "es"

# key -> {"es": "...", "en": "..."}. Placeholders use str.format() syntax.
_STRINGS: dict[str, dict[str, str]] = {
    "pf.net_worth": {
        "es": "Patrimonio neto: todo lo que tienes en tus cuentas, menos todo lo que debes en tarjetas y préstamos.",
        "en": "Net worth: everything you have in your accounts, minus everything you owe on cards and loans.",
    },
    "pf.recurring": {
        "es": "Cargos recurrentes detectados por mismo beneficiario, monto similar (±15%), cadencia de 20-40 días.",
        "en": "Recurring bills detected from same payee, similar amount (±15%), 20-40 day cadence.",
    },
    "pf.budget_status": {
        "es": "{name}: gastado / (presupuesto + remanente).",
        "en": "{name}: spent / (budget + rollover).",
    },
    "pf.goal_monthly_required": {
        "es": "monthly_required = (meta − progreso) / meses restantes a la fecha objetivo.",
        "en": "monthly_required = (target − progress) / months remaining to target_date.",
    },
    "pf.goal_projection": {
        "es": "La proyección asume una aportación mensual constante igual a monthly_required.",
        "en": "Projection assumes a constant monthly contribution equal to monthly_required.",
    },
    "pf.goal_debt_whatif": {
        "es": "Un pago mensual extra reduce los meses para liquidar la deuda y el interés total pagado.",
        "en": "Extra monthly payment reduces months-to-payoff and total interest paid.",
    },
    "pf.income_smoothed": {
        "es": "El promedio de 6 meses de ingreso irregular es la media del ingreso bruto de los últimos {months} meses.",
        "en": "Irregular-income 6-month average is the mean of gross income over the last {months} months.",
    },
    "pf.review": {
        "es": "La revisión mensual agrega los movimientos del período; deltas vs. el mes anterior.",
        "en": "Monthly review aggregates ledger postings for the period; deltas vs. prior month.",
    },
    "pf.card_status": {
        "es": (
            "Pago para no generar intereses = saldo al corte; el pago mínimo lo define el emisor de la "
            "tarjeta, no se calcula aquí (verificar con el contrato de la tarjeta)."
        ),
        "en": (
            "Payment to avoid interest = statement (cut-date) balance in full; minimum payment is a "
            "card-issuer policy, not computed here (verify with your card agreement)."
        ),
    },
    "pf.loan_amortization": {
        "es": "Pago mensual fijo (pmt) que amortiza el principal en `months` meses a annual_rate/12.",
        "en": "Fixed monthly payment (pmt) amortizing principal over `months` at annual_rate/12.",
    },
    "pf.loan_whatif": {
        "es": "Un pago mensual extra acorta el plazo y reduce el interés total pagado.",
        "en": "Extra monthly payment shortens payoff and lowers total interest paid.",
    },
    "tax.prefill_summary": {
        "es": (
            "Prellenado esperado para {period}: ingreso {income}, ISR {isr}, "
            "IVA acreditable {iva_acreditable} {currency}."
        ),
        "en": (
            "Expected SAT prefill for {period}: income {income}, ISR {isr}, "
            "creditable IVA {iva_acreditable} {currency}."
        ),
    },
    "tax.prefill_step_income": {"es": "Ingreso que el SAT dará por cobrado", "en": "Income the SAT will assume collected"},
    "tax.prefill_step_isr": {"es": "ISR que mostrará el prellenado", "en": "ISR the prefill will show"},
    "tax.prefill_step_iva": {"es": "IVA acreditable del prellenado", "en": "Creditable IVA in the prefill"},
    "tax.prefill_formula_iva": {
        "es": "sólo gastos generales pagados por medios bancarios",
        "en": "only general expenses paid through bank methods",
    },
    "tax.warning_mismatch": {
        "es": "El prellenado del SAT y la realidad bancaria no coinciden: revisa las diferencias antes de declarar.",
        "en": "The SAT prefill and bank reality do not match: review the differences before filing.",
    },
    "tax.warning_draft": {
        "es": "Borrador. Aurum nunca transmite ni firma una declaración.",
        "en": "Draft. Aurum never transmits or signs a filing.",
    },
    "tax.diff.pue_not_collected": {
        "es": (
            "{count} factura(s) PUE que el SAT da por cobradas nunca llegaron al banco ({total} {currency}). "
            "El ISR se paga igual; emite PPD la próxima vez."
        ),
        "en": (
            "{count} PUE invoice(s) the SAT assumes collected never reached the bank ({total} {currency}). "
            "ISR is still owed; issue PPD next time."
        ),
    },
    "tax.diff.ppd_missing_rep": {
        "es": (
            "{count} factura(s) PPD sin complemento de pago ({total} {currency}): "
            "no se declaran hasta que exista el REP."
        ),
        "en": (
            "{count} PPD invoice(s) with no payment complement ({total} {currency}): "
            "not declared until the REP exists."
        ),
    },
    "tax.diff.deposit_without_cfdi": {
        "es": (
            "{count} depósito(s) sin CFDI que los respalde ({total} {currency}). "
            "En RESICO todo ingreso debe facturarse."
        ),
        "en": (
            "{count} deposit(s) with no backing CFDI ({total} {currency}). "
            "Under RESICO every deposit must be invoiced."
        ),
    },
    "tax.diff.cash_paid_expense": {
        "es": "IVA no acreditable por pagado en efectivo — el IVA no es acreditable (LIVA art. 5): {total} {currency}.",
        "en": "IVA not creditable — paid in cash (LIVA art. 5): {total} {currency}.",
    },
    "tax.diff.fixed_asset_iva": {
        "es": (
            "IVA no acreditable por inversión/activo fijo — el prellenado del SAT deja fuera este IVA: "
            "{total} {currency}."
        ),
        "en": "IVA not in the prefill — investment/fixed asset: {total} {currency}.",
    },
    "ledger.statements.pnl": {
        "es": "Estado de resultados para {period}: ingresos menos gastos, por cuenta.",
        "en": "Profit & loss for {period}: income minus expenses, by account.",
    },
    "ledger.statements.balance": {
        "es": "Balance general al cierre de {period}: activos, pasivos y capital.",
        "en": "Balance sheet as of {period} end: assets, liabilities, and equity.",
    },
    "ledger.statements.cashflow": {
        "es": "Flujo de efectivo para {period}: cambio en cuentas de banco/efectivo por contracuenta.",
        "en": "Cash flow for {period}: change in bank/cash accounts by counter-account.",
    },
    "ledger.txn.updated": {
        "es": "Transacción {txn_id} reescrita; el historial anterior no se conserva en el archivo.",
        "en": "Transaction {txn_id} rewritten; the prior text is not kept in the file.",
    },
    "ledger.txn.voided": {
        "es": "Movimiento {txn_id} anulado: se marcó #voided y se agregó un movimiento de reversa; nada se borró.",
        "en": "Transaction {txn_id} voided: tagged #voided and a reversing entry was appended; nothing erased.",
    },
    "ingest.reconcile": {
        "es": "Sugerencias por monto (±1%) y fecha (±3 días) contra transacciones y CFDIs.",
        "en": "Suggestions by amount (±1%) and date (±3 days) against ledger transactions and CFDIs.",
    },
    # ------------------------------------------------------------------ shared rule disclaimer
    "rules.not_advice": {
        "es": "Solo informativo — Aurum no es una declaración de impuestos ni asesoría fiscal; revísalo con un preparador con licencia.",
        "en": "Informational only — Aurum is not a tax return and not tax advice; review with a licensed preparer.",
    },
    "rules.xb.not_advice": {
        "es": "Solo informativo — la residencia, la posición del tratado y las obligaciones de FBAR deben confirmarse con un preparador especializado en temas transfronterizos; Aurum no decide nada.",
        "en": "Informational only — residency, treaty positions and FBAR obligations must be confirmed with a cross-border preparer; Aurum decides nothing.",
    },
    # ------------------------------------------------------------------ rules.us.fed (federal.py)
    "rules.us.fed.schedule_c.summary": {
        "es": "Utilidad neta del Anexo C del año: {net} {currency} (ingresos brutos {gross} − devoluciones {returns} − costo de ventas {cogs} − gastos {exp_total}). {not_advice}",
        "en": "Schedule C net profit for the year: {net} {currency} (gross {gross} − returns {returns} − COGS {cogs} − expenses {exp_total}). {not_advice}",
    },
    "rules.us.fed.schedule_c.step.gross_receipts": {"es": "Ingresos brutos o ventas (línea 1)", "en": "Gross receipts or sales (line 1)"},
    "rules.us.fed.schedule_c.step.returns": {"es": "Devoluciones y bonificaciones (línea 2)", "en": "Returns and allowances (line 2)"},
    "rules.us.fed.schedule_c.step.cogs": {"es": "Costo de ventas (línea 4)", "en": "Cost of goods sold (line 4)"},
    "rules.us.fed.schedule_c.step.expense": {"es": "Gasto · {name}", "en": "Expense · {name}"},
    "rules.us.fed.schedule_c.step.total_expenses": {"es": "Total de gastos (línea 28)", "en": "Total expenses (line 28)"},
    "rules.us.fed.schedule_c.step.net_profit": {"es": "Utilidad neta o (pérdida) (línea 31)", "en": "Net profit or (loss) (line 31)"},
    "rules.us.fed.schedule_c.step.loss_label": {"es": "Pérdida", "en": "Loss"},
    "rules.us.fed.schedule_c.step.loss_note": {
        "es": "una pérdida del Anexo C no genera impuesto de trabajo por cuenta propia; aplican límites de riesgo y de pérdidas pasivas (verificar con un preparador)",
        "en": "a Schedule C loss does not produce self-employment tax; at-risk and passive-loss limits apply (verify with a preparer)",
    },
    "rules.us.fed.se_tax.summary": {
        "es": "Impuesto de trabajo por cuenta propia 2026: {total} {currency} (OASDI {oasdi} + Medicare {medicare} + Medicare adicional {additional}){mark}. {not_advice}",
        "en": "Self-employment tax for 2026: {total} {currency} (OASDI {oasdi} + Medicare {medicare} + additional Medicare {additional}){mark}. {not_advice}",
    },
    "rules.us.fed.se_tax.step.schedule_c_net": {"es": "Utilidad neta del Anexo C", "en": "Schedule C net profit"},
    "rules.us.fed.se_tax.step.net_earnings": {"es": "Ingreso neto de trabajo por cuenta propia", "en": "Net earnings from self-employment"},
    "rules.us.fed.se_tax.step.w2_wages": {"es": "Salarios W-2 ya sujetos a FICA", "en": "W-2 wages already subject to FICA"},
    "rules.us.fed.se_tax.step.wage_base": {"es": "Base salarial del Seguro Social 2026", "en": "Social Security wage base 2026"},
    "rules.us.fed.se_tax.step.oasdi_base": {"es": "Base sujeta a la porción OASDI del 12.4%", "en": "Base subject to the 12.4% OASDI portion"},
    "rules.us.fed.se_tax.step.oasdi": {"es": "Porción OASDI", "en": "OASDI portion"},
    "rules.us.fed.se_tax.step.medicare": {"es": "Porción Medicare", "en": "Medicare portion"},
    "rules.us.fed.se_tax.step.addl_threshold": {"es": "Umbral de Medicare adicional ({status})", "en": "Additional Medicare threshold ({status})"},
    "rules.us.fed.se_tax.step.addl_medicare": {"es": "Impuesto de Medicare adicional", "en": "Additional Medicare tax"},
    "rules.us.fed.se_tax.step.total": {"es": "Impuesto de trabajo por cuenta propia", "en": "Self-employment tax"},
    "rules.us.fed.se_tax.step.deductible_half": {
        "es": "Mitad deducible (ajuste al ingreso, § 164(f))",
        "en": "Deductible half (adjustment to income, § 164(f))",
    },
    "rules.us.fed.income_tax.summary": {
        "es": "Impuesto federal sobre la renta 2026 ({status}): {tax} {currency} sobre ingreso gravable {taxable}; tasa marginal {marginal}, tasa efectiva {effective}%. {not_advice}",
        "en": "Federal income tax for 2026 ({status}): {tax} {currency} on taxable income {taxable}; marginal rate {marginal}, effective {effective}%. {not_advice}",
    },
    "rules.us.fed.income_tax.step.other_income": {"es": "Otros ingresos", "en": "Other income"},
    "rules.us.fed.income_tax.step.less_se": {
        "es": "Menos: mitad deducible del impuesto de trabajo por cuenta propia (§ 164(f))",
        "en": "Less: deductible half of SE tax (§ 164(f))",
    },
    "rules.us.fed.income_tax.step.less_adjustments": {"es": "Menos: otros ajustes", "en": "Less: other adjustments"},
    "rules.us.fed.income_tax.step.agi": {"es": "Ingreso bruto ajustado", "en": "Adjusted gross income"},
    "rules.us.fed.income_tax.deduction_kind.standard": {"es": "Estándar", "en": "Standard"},
    "rules.us.fed.income_tax.deduction_kind.itemized": {"es": "Detallada", "en": "Itemized"},
    "rules.us.fed.income_tax.deduction_kind.given": {"es": "Dada", "en": "Given"},
    "rules.us.fed.income_tax.step.deduction": {"es": "Deducción {kind} ({status})", "en": "{kind} deduction ({status})"},
    "rules.us.fed.income_tax.step.taxable_income": {"es": "Ingreso gravable", "en": "Taxable income"},
    "rules.us.fed.income_tax.step.bracket": {"es": "Tramo al {rate}", "en": "Bracket at {rate}"},
    "rules.us.fed.income_tax.step.income_tax": {"es": "Impuesto sobre la renta", "en": "Income tax"},
    "rules.us.fed.income_tax.step.marginal_rate": {"es": "Tasa marginal", "en": "Marginal rate"},
    "rules.us.fed.step.not_modelled": {"es": "No modelado", "en": "Not modelled"},
    "rules.us.fed.income_tax.step.not_modelled_note": {
        "es": "créditos, QBI (§ 199A), NIIT, AMT, tasas de ganancias de capital y adiciones estatales — consulta a un preparador",
        "en": "credits, QBI (§ 199A), NIIT, AMT, capital-gain rates and state add-backs — ask a preparer",
    },
    "rules.us.fed.quarterly.summary": {
        "es": "Pago estimado: {each} {currency} por trimestre ({remaining} para el año, {basis}). {not_advice}",
        "en": "Estimated tax: {each} {currency} per quarter ({remaining} for the year, {basis}). {not_advice}",
    },
    "rules.us.fed.quarterly.basis.no_prior": {
        "es": "{pct} del impuesto del año actual (no se proporcionó declaración del año anterior)",
        "en": "{pct} of the current year's tax (no prior-year return supplied)",
    },
    "rules.us.fed.quarterly.basis.safe_harbor": {
        "es": "{pct} del impuesto del año anterior (refugio seguro)",
        "en": "{pct} of the prior year's tax (safe harbour)",
    },
    "rules.us.fed.quarterly.basis.current_year": {
        "es": "{pct} del impuesto del año actual",
        "en": "{pct} of the current year's tax",
    },
    "rules.us.fed.quarterly.step.projected_tax": {
        "es": "Impuesto proyectado para 2026 (impuesto sobre la renta + de trabajo por cuenta propia)",
        "en": "Projected tax for 2026 (income tax + SE tax)",
    },
    "rules.us.fed.quarterly.step.pct_current": {"es": "{pct} del impuesto del año actual", "en": "{pct} of the current year's tax"},
    "rules.us.fed.quarterly.step.prior_tax": {"es": "Impuesto del año anterior", "en": "Prior year's tax"},
    "rules.us.fed.quarterly.step.prior_agi": {"es": "Ingreso bruto ajustado del año anterior", "en": "Prior year's AGI"},
    "rules.us.fed.quarterly.unknown": {"es": "desconocido", "en": "unknown"},
    "rules.us.fed.quarterly.step.safe_harbor_threshold": {
        "es": "Umbral de refugio seguro del año anterior",
        "en": "Prior-year safe-harbour threshold",
    },
    "rules.us.fed.quarterly.step.safe_harbor_note": {
        "es": "por encima de él, la parte del año anterior es 110% en lugar de 100% (§ 6654(d)(1)(C))",
        "en": "above it the prior-year leg is 110% instead of 100% (§ 6654(d)(1)(C))",
    },
    "rules.us.fed.quarterly.step.required_annual": {"es": "Pago anual requerido", "en": "Required annual payment"},
    "rules.us.fed.quarterly.step.less_withholding": {"es": "Menos: retención ya pagada", "en": "Less: withholding already paid"},
    "rules.us.fed.quarterly.step.to_pay": {"es": "A pagar en cuotas", "en": "To pay in installments"},
    "rules.us.fed.quarterly.step.each_installment": {"es": "Cada cuota", "en": "Each installment"},
    "rules.us.fed.quarterly.step.installment_due": {"es": "Cuota {i} vence", "en": "Installment {i} due"},
    "rules.us.fed.quarterly.step.due_dates": {"es": "Fechas límite", "en": "Due dates"},
    "rules.us.fed.quarterly.step.due_dates_note": {
        "es": "cada una se recorre al siguiente día hábil si cae en fin de semana o día feriado (verificar)",
        "en": "each shifts to the next business day when it falls on a weekend or legal holiday (verify)",
    },
    "rules.us.fed.quarterly.step.no_penalty": {"es": "No se espera penalización", "en": "No penalty expected"},
    "rules.us.fed.quarterly.step.no_penalty_note": {
        "es": "el impuesto después de la retención está por debajo del mínimo de minimis de {de_minimis} del § 6654(e)(1)",
        "en": "tax after withholding is below the {de_minimis} de-minimis of § 6654(e)(1)",
    },
    # ------------------------------------------------------------------ rules.us.tx (texas.py)
    "rules.us.tx.franchise.summary": {
        "es": "Impuesto de franquicia de Texas 2026: {verdict} — {reason}{mark}. {not_advice}",
        "en": "Texas franchise tax 2026: {verdict} — {reason}{mark}. {not_advice}",
    },
    "rules.us.tx.franchise.verdict.no_tax_due": {"es": "sin impuesto a pagar", "en": "no tax due"},
    "rules.us.tx.franchise.verdict.tax_due": {"es": "impuesto de franquicia {tax} {currency}", "en": "franchise tax {tax} {currency}"},
    "rules.us.tx.franchise.step.total_revenue": {"es": "Ingresos totales anualizados", "en": "Annualized total revenue"},
    "rules.us.tx.franchise.step.taxable_entity": {"es": "Entidad sujeta a impuesto", "en": "Taxable entity"},
    "rules.us.tx.franchise.step.no_tax_due_threshold": {"es": "Umbral de no impuesto a pagar (2026)", "en": "No-tax-due threshold (2026)"},
    "rules.us.tx.franchise.step.margin": {"es": "Margen — el más bajo de las cuatro opciones", "en": "Margin — lowest of the four options"},
    "rules.us.tx.franchise.step.apportioned": {"es": "Prorrateado a Texas", "en": "Apportioned to Texas"},
    "rules.us.tx.franchise.step.rate": {"es": "Tasa", "en": "Rate"},
    "rules.us.tx.franchise.rate_kind.retail_wholesale": {"es": "menudeo/mayoreo", "en": "retail/wholesale"},
    "rules.us.tx.franchise.rate_kind.other": {"es": "otro", "en": "other"},
    "rules.us.tx.franchise.step.ez": {"es": "Alternativa de cálculo E-Z", "en": "E-Z computation alternative"},
    "rules.us.tx.franchise.step.compensation_limit": {
        "es": "Límite de deducción de compensación por persona (2026)",
        "en": "Compensation deduction limit per person (2026)",
    },
    "rules.us.tx.franchise.step.tax_due": {"es": "Impuesto de franquicia a pagar", "en": "Franchise tax due"},
    "rules.us.tx.franchise.step.still_required": {"es": "Aún se requiere", "en": "Still required"},
    "rules.us.tx.franchise.step.not_modelled": {
        "es": "grupos combinados, entidades pasivas, sociedades escalonadas y las reglas de origen del prorrateo",
        "en": "combined groups, passive entities, tiered partnerships and the apportionment sourcing rules",
    },
    "rules.us.tx.franchise.reason.sole_prop": {
        "es": "una empresa unipersonal (no una LLC) no es una entidad sujeta a impuesto conforme a Tex. Tax Code § 171.0002(b)(1)",
        "en": "a sole proprietorship (not an LLC) is not a taxable entity under Tex. Tax Code § 171.0002(b)(1)",
    },
    "rules.us.tx.franchise.reason.below_threshold": {
        "es": "los ingresos totales anualizados {revenue} están en o por debajo del umbral 2026 de no impuesto a pagar {threshold}",
        "en": "annualized total revenue {revenue} is at or below the 2026 no-tax-due threshold {threshold}",
    },
    "rules.us.tx.franchise.reason.above_threshold": {
        "es": "los ingresos totales anualizados {revenue} están por arriba del umbral 2026 de no impuesto a pagar {threshold}",
        "en": "annualized total revenue {revenue} is above the 2026 no-tax-due threshold {threshold}",
    },
    "rules.us.tx.franchise.report.pir": {
        "es": "Reporte de Información Pública (PIR) o Reporte de Información de Propiedad (OIR)",
        "en": "Public Information Report (PIR) or Ownership Information Report (OIR)",
    },
    "rules.us.tx.franchise.report.franchise_and_pir": {
        "es": "Reporte de impuesto de franquicia",
        "en": "Franchise tax report",
    },
    "rules.us.tx.franchise.margin.revenue_share": {"es": "70% de los ingresos totales", "en": "70% of total revenue"},
    "rules.us.tx.franchise.margin.less_cogs": {"es": "ingresos totales − costo de ventas", "en": "total revenue − cost of goods sold"},
    "rules.us.tx.franchise.margin.less_compensation": {"es": "ingresos totales − compensación", "en": "total revenue − compensation"},
    "rules.us.tx.franchise.margin.flat": {"es": "ingresos totales − USD 1,000,000", "en": "total revenue − USD 1,000,000"},
    "rules.us.tx.sales_use.summary": {
        "es": "Impuesto sobre ventas y uso de Texas a {rate}: {total} {currency} (ventas {sales} + uso {use}). {not_advice}",
        "en": "Texas sales & use tax at {rate}: {total} {currency} (sales {sales} + use {use}). {not_advice}",
    },
    "rules.us.tx.sales_use.step.state_rate": {"es": "Tasa estatal", "en": "State rate"},
    "rules.us.tx.sales_use.step.local_rate": {"es": "Tasa local aplicada", "en": "Local rate applied"},
    "rules.us.tx.sales_use.step.combined_rate": {"es": "Tasa combinada", "en": "Combined rate"},
    "rules.us.tx.sales_use.step.combined_rate_note": {"es": "la tasa combinada máxima es {max_rate}", "en": "maximum combined rate is {max_rate}"},
    "rules.us.tx.sales_use.step.taxable_sales": {"es": "Ventas gravables", "en": "Taxable sales"},
    "rules.us.tx.sales_use.step.sales_tax": {"es": "Impuesto sobre ventas", "en": "Sales tax"},
    "rules.us.tx.sales_use.step.out_of_state": {"es": "Compras foráneas usadas en Texas", "en": "Out-of-state purchases used in Texas"},
    "rules.us.tx.sales_use.step.use_tax": {"es": "Impuesto de uso", "en": "Use tax"},
    "rules.us.tx.sales_use.step.use_tax_note": {
        "es": "la contraparte que se debe cuando no se cobró impuesto de Texas al comprar (§ 151.101)",
        "en": "the counterpart owed when no Texas tax was collected at purchase (§ 151.101)",
    },
    "rules.us.tx.sales_use.step.total": {"es": "Total", "en": "Total"},
    "rules.us.tx.sales_use.step.capped": {
        "es": "la tasa local solicitada excedió el 2% y fue limitada",
        "en": "the requested local rate exceeded 2% and was capped",
    },
    "rules.us.tx.sales_use.step.capped_label": {"es": "Tasa local limitada", "en": "Local rate capped"},
    "rules.us.tx.sales_use.step.services_note_label": {
        "es": "Los servicios no son gravables automáticamente",
        "en": "Services are not automatically taxable",
    },
    "rules.us.tx.sales_use.step.services_note": {
        "es": "solo los servicios gravables listados en § 151.0101; los servicios profesionales generalmente no se gravan (verificar)",
        "en": "only the taxable services listed in § 151.0101; professional services are generally not taxed (verify)",
    },
    "rules.us.tx.sales_use.step.not_modelled": {
        "es": "certificados de exención, certificados de reventa, nexo y la búsqueda de jurisdicción local por dirección",
        "en": "exemption certificates, resale certificates, nexus and the local-jurisdiction lookup by address",
    },
    # ------------------------------------------------------------------ rules.crossborder (xb)
    "rules.xb.residency.verdict.dual": {"es": "residente de México y Estados Unidos con estos datos", "en": "resident of both Mexico and the US on these facts"},
    "rules.xb.residency.verdict.us": {"es": "residente fiscal de EE. UU.", "en": "US tax resident"},
    "rules.xb.residency.verdict.mx": {"es": "residente fiscal de México", "en": "Mexican tax resident"},
    "rules.xb.residency.verdict.neither": {"es": "ninguno, con estos datos", "en": "neither, on these facts"},
    "rules.xb.residency.summary": {
        "es": "Residencia: {verdict}. Días ponderados en EE. UU. {weighted} vs. el umbral de 183{mark}. {not_advice}",
        "en": "Residency: {verdict}. Weighted US days {weighted} vs the 183 threshold{mark}. {not_advice}",
    },
    "rules.xb.residency.step.days_current": {"es": "Días en EE. UU., año actual", "en": "Days in the US, current year"},
    "rules.xb.residency.step.days_prior1": {"es": "Días en EE. UU., primer año anterior", "en": "Days in the US, first preceding year"},
    "rules.xb.residency.step.days_prior1_note": {"es": "contados a 1/3", "en": "counted at 1/3"},
    "rules.xb.residency.step.days_prior2": {"es": "Días en EE. UU., segundo año anterior", "en": "Days in the US, second preceding year"},
    "rules.xb.residency.step.days_prior2_note": {"es": "contados a 1/6", "en": "counted at 1/6"},
    "rules.xb.residency.step.weighted_days": {"es": "Días ponderados", "en": "Weighted days"},
    "rules.xb.residency.step.weighted_days_note": {
        "es": "actual + anterior/3 + segundo anterior/6 (§ 7701(b)(3)(A)(ii), umbral {threshold})",
        "en": "current + prior/3 + second prior/6 (§ 7701(b)(3)(A)(ii), threshold {threshold})",
    },
    "rules.xb.residency.step.spt_met": {"es": "Prueba de presencia sustancial cumplida", "en": "Substantial presence test met"},
    "rules.xb.residency.step.us_resident": {"es": "Residente fiscal de EE. UU.", "en": "US tax resident"},
    "rules.xb.residency.step.days_mx": {"es": "Días en México", "en": "Days in Mexico"},
    "rules.xb.residency.step.casa_habitacion": {"es": "Casa habitación en México / en EE. UU.", "en": "Casa habitación in Mexico / in the US"},
    "rules.xb.residency.step.mx_resident": {"es": "Residente fiscal de México", "en": "Mexican tax resident"},
    "rules.xb.residency.step.dual": {"es": "Doble residencia", "en": "Dual residency"},
    "rules.xb.residency.step.note": {"es": "Nota", "en": "Note"},
    "rules.xb.residency.basis.us_citizen": {
        "es": "ciudadano de EE. UU. — gravado sobre el ingreso mundial sin importar dónde viva",
        "en": "US citizen — taxed on worldwide income regardless of where you live",
    },
    "rules.xb.residency.basis.green_card": {
        "es": "residente permanente legal (prueba de tarjeta verde, § 7701(b)(1)(A)(i))",
        "en": "lawful permanent resident (green-card test, § 7701(b)(1)(A)(i))",
    },
    "rules.xb.residency.basis.spt_met": {
        "es": "prueba de presencia sustancial cumplida: {days_us} días este año (≥ 31) y {weighted} días ponderados (≥ {threshold})",
        "en": "substantial presence test met: {days_us} days this year (≥ 31) and {weighted} weighted days (≥ {threshold})",
    },
    "rules.xb.residency.basis.spt_not_met": {
        "es": "prueba de presencia sustancial no cumplida: {days_us} días este año, {weighted} días ponderados",
        "en": "substantial presence test not met: {days_us} days this year, {weighted} weighted days",
    },
    "rules.xb.residency.note.nonresident_1040nr": {
        "es": "un no residente con ingreso de fuente estadounidense puede tener obligación de presentar el Formulario 1040-NR (verificar)",
        "en": "a non-resident with US-source income may still have a Form 1040-NR obligation (verify)",
    },
    "rules.xb.residency.note.closer_connection": {
        "es": "la excepción de conexión más cercana (§ 7701(b)(3)(B), Formulario 8840) puede anular la presencia sustancial por debajo de 183 días en el año actual — explórala con un preparador (verificar)",
        "en": "the closer-connection exception (§ 7701(b)(3)(B), Form 8840) can undo substantial presence below 183 days in the current year — explore it with a preparer (verify)",
    },
    "rules.xb.residency.mx_basis.home_only_mx": {
        "es": "casa habitación en México y en ningún otro lugar (CFF art. 9, fr. I)",
        "en": "casa habitación in Mexico and nowhere else (CFF art. 9, fr. I)",
    },
    "rules.xb.residency.mx_basis.vital_interests": {
        "es": "casas en ambos países; centro de intereses vitales en México — más del 50% del ingreso es de fuente mexicana ({share}) (CFF art. 9, fr. I, a) (verificar)",
        "en": "homes in both countries; centre of vital interests in Mexico — more than 50% of income is Mexican-source ({share}) (CFF art. 9, fr. I, a) (verify)",
    },
    "rules.xb.residency.mx_basis.professional_center": {
        "es": "casas en ambos países; el centro principal de actividades profesionales está en México (CFF art. 9, fr. I, b) (verificar)",
        "en": "homes in both countries; main centre of professional activities is in Mexico (CFF art. 9, fr. I, b) (verify)",
    },
    "rules.xb.residency.mx_basis.no_vital_interests": {
        "es": "casas en ambos países y el centro de intereses vitales no apunta a México con los datos proporcionados (CFF art. 9) (verificar)",
        "en": "homes in both countries and the centre of vital interests does not point to Mexico on the facts supplied (CFF art. 9) (verify)",
    },
    "rules.xb.residency.mx_basis.no_home": {
        "es": "sin casa habitación en México con los datos proporcionados (CFF art. 9)",
        "en": "no casa habitación in Mexico on the facts supplied (CFF art. 9)",
    },
    "rules.xb.residency.note.days_mx_signal": {
        "es": "{days_mx} días en México es una señal práctica fuerte aunque el CFF art. 9 depende de la casa y el centro de intereses vitales y no de un conteo de días (verificar)",
        "en": "{days_mx} days in Mexico is a strong practical signal even though CFF art. 9 turns on the home and the centre of vital interests rather than on a day count (verify)",
    },
    "rules.xb.residency.note.presumed_continue": {
        "es": "se presume que la residencia mexicana continúa hasta que se presente un aviso de cambio de residencia (verificar)",
        "en": "Mexican residence is presumed to continue until a change-of-residence notice is filed (verify)",
    },
    "rules.xb.tiebreaker.label.permanent_home": {"es": "Vivienda permanente disponible en un solo Estado", "en": "Permanent home available in only one State"},
    "rules.xb.tiebreaker.label.center_of_vital_interests": {"es": "Centro de intereses vitales (relaciones personales y económicas)", "en": "Centre of vital interests (personal and economic relations)"},
    "rules.xb.tiebreaker.label.habitual_abode": {"es": "Morada habitual", "en": "Habitual abode"},
    "rules.xb.tiebreaker.label.nationality": {"es": "Nacionalidad", "en": "Nationality"},
    "rules.xb.tiebreaker.label.competent_authority": {"es": "Acuerdo mutuo entre las autoridades competentes", "en": "Mutual agreement between the competent authorities"},
    "rules.xb.tiebreaker.summary.not_applicable": {
        "es": "El desempate del tratado no aplica: no eres residente en ambos países con estos datos.",
        "en": "Treaty tie-breaker does not apply: you are not resident in both countries on these facts.",
    },
    "rules.xb.tiebreaker.summary.resolved": {
        "es": "Doble residencia: la escalera del art. 4 apunta a {country} en el paso {step} ({label}){mark}.",
        "en": "Dual residency: the art. 4 ladder points to {country} at step {step} ({label}){mark}.",
    },
    "rules.xb.tiebreaker.summary.unresolved": {
        "es": "Doble residencia y ningún paso de la escalera del art. 4 está respondido — el desempate no está resuelto con estos datos{mark}.",
        "en": "Dual residency and no step of the art. 4 ladder is answered — the tie-breaker is unresolved on these facts{mark}.",
    },
    "rules.xb.tiebreaker.step.dual_resident": {"es": "Residente de ambos países", "en": "Resident of both countries"},
    "rules.xb.tiebreaker.step.step_label": {"es": "Paso {step} · {label}", "en": "Step {step} · {label}"},
    "rules.xb.tiebreaker.answer.unanswered": {"es": "sin responder", "en": "unanswered"},
    "rules.xb.tiebreaker.answer.decisive": {"es": "decisivo", "en": "decisive"},
    "rules.xb.tiebreaker.answer.not_decisive": {"es": "no decisivo con estos datos", "en": "not decisive on these facts"},
    "rules.xb.tiebreaker.step.cost_label": {"es": "Lo que cuesta una posición de tratado", "en": "What a treaty position costs"},
    "rules.xb.tiebreaker.step.cost_note": {
        "es": "reclamarla requiere el Formulario 8833 y puede cambiar el estatus de declaración, FBAR y FATCA — nunca la tomes sin un preparador",
        "en": "claiming it requires Form 8833 and can change filing status, FBAR and FATCA duties — never take it without a preparer",
    },
    "rules.xb.fbar.verdict.required": {"es": "es probable que se requiera un FBAR", "en": "an FBAR is likely required"},
    "rules.xb.fbar.verdict.not_required": {"es": "no parece requerirse un FBAR", "en": "no FBAR appears to be required"},
    "rules.xb.fbar.summary": {
        "es": "Las cuentas extranjeras alcanzan un máximo de {aggregate} USD contra el umbral de {threshold} USD — {verdict}. {not_advice}",
        "en": "Foreign accounts peak at {aggregate} USD against the {threshold} USD threshold — {verdict}. {not_advice}",
    },
    "rules.xb.fbar.step.us_person": {"es": "Persona de EE. UU.", "en": "US person"},
    "rules.xb.fbar.step.account": {"es": "Cuenta · {country} {institution}", "en": "Account · {country} {institution}"},
    "rules.xb.fbar.step.account_note": {"es": "saldo más alto en cualquier momento del año calendario", "en": "highest balance at any point in the calendar year"},
    "rules.xb.fbar.step.aggregate": {"es": "Máximo agregado", "en": "Aggregate maximum"},
    "rules.xb.fbar.step.aggregate_note": {"es": "Σ del saldo más alto de cada cuenta", "en": "Σ of each account's highest balance"},
    "rules.xb.fbar.step.threshold": {"es": "Umbral", "en": "Threshold"},
    "rules.xb.fbar.step.threshold_note": {"es": "31 C.F.R. § 1010.350 — superado en cualquier momento", "en": "31 C.F.R. § 1010.350 — exceeded at any time"},
    "rules.xb.fbar.step.required": {"es": "FBAR requerido", "en": "FBAR required"},
    "rules.xb.fbar.step.deadline": {"es": "Fecha límite", "en": "Deadline"},
    "rules.xb.fbar.step.deadline_value": {
        "es": "{due}, extensión automática al {extension}",
        "en": "{due}, automatic extension to {extension}",
    },
    "rules.xb.fbar.step.not_fatca_label": {"es": "No es lo mismo que FATCA", "en": "Not the same as FATCA"},
    "rules.xb.fbar.step.not_fatca_note": {
        "es": "el Formulario 8938 (§ 6038D) tiene umbrales distintos y más altos y se presenta con la declaración — revisa ambos",
        "en": "Form 8938 (§ 6038D) has different, higher thresholds and is filed with the return — check both",
    },
    "rules.xb.feie.summary": {
        "es": "El FEIE podría excluir {available} USD (tope 2026 {cap}); el impuesto extranjero pagado de {paid} USD es la base de la que partiría un crédito fiscal extranjero{mark}. Explora ambos con un preparador — Aurum no elige. {not_advice}",
        "en": "FEIE could exclude {available} USD (2026 cap {cap}); foreign tax paid of {paid} USD is what a foreign tax credit would work from{mark}. Explore both with a preparer — Aurum does not choose. {not_advice}",
    },
    "rules.xb.feie.basis.bona_fide": {"es": "prueba de residente de buena fe (§ 911(d)(1)(A))", "en": "bona fide residence test (§ 911(d)(1)(A))"},
    "rules.xb.feie.basis.physical": {
        "es": "prueba de presencia física: {days} días completos en el extranjero (≥ {min_days})",
        "en": "physical presence test: {days} full days abroad (≥ {min_days})",
    },
    "rules.xb.feie.basis.neither": {
        "es": "ninguna prueba se cumple con estos datos: {days} días en el extranjero y no es residente de buena fe",
        "en": "neither test met on these facts: {days} days abroad and not a bona fide resident",
    },
    "rules.xb.feie.step.foreign_income": {"es": "Ingreso ganado en el extranjero", "en": "Foreign earned income"},
    "rules.xb.feie.step.cap": {"es": "Tope de exclusión 2026", "en": "2026 exclusion cap"},
    "rules.xb.feie.step.qualifies": {"es": "Califica para la exclusión", "en": "Qualifies for the exclusion"},
    "rules.xb.feie.step.available": {"es": "Exclusión disponible", "en": "Exclusion available"},
    "rules.xb.feie.step.available_note": {"es": "mín(ingreso ganado en el extranjero, tope)", "en": "min(foreign earned income, cap)"},
    "rules.xb.feie.step.tax_paid": {"es": "Impuesto extranjero sobre la renta pagado", "en": "Foreign income tax paid"},
    "rules.xb.feie.step.option": {"es": "Opción · {option} ({citation})", "en": "Option · {option} ({citation})"},
    "rules.xb.feie.option.feie.what": {
        "es": "excluye el ingreso ganado en el extranjero del ingreso gravable de EE. UU., hasta el tope anual",
        "en": "excludes foreign earned income from US taxable income, up to the annual cap",
    },
    "rules.xb.feie.option.feie.watch": {
        "es": "no reduce el impuesto de trabajo por cuenta propia, no se puede combinar con un crédito por impuesto sobre el mismo ingreso, y revocar la elección te bloquea por cinco años",
        "en": "does not reduce self-employment tax, cannot be combined with a credit for tax on the same income, and revoking the election locks you out for five years",
    },
    "rules.xb.feie.option.ftc.what": {
        "es": "acredita el impuesto extranjero sobre la renta ya pagado contra el impuesto de EE. UU. sobre el mismo ingreso",
        "en": "credits foreign income tax already paid against the US tax on the same income",
    },
    "rules.xb.feie.option.ftc.watch": {
        "es": "limitado por la fórmula del § 904 y separado en categorías; el crédito no usado se traslada 1 año hacia atrás y 10 hacia adelante",
        "en": "limited by the § 904 formula and separated into baskets; unused credit carries back 1 year and forward 10",
    },
    "rules.xb.feie.step.no_se_relief_label": {"es": "Ninguna opción afecta el impuesto de trabajo por cuenta propia", "en": "Neither option touches self-employment tax"},
    "rules.xb.feie.step.no_se_relief_note": {
        "es": "un ciudadano de EE. UU. que trabaja por cuenta propia en el extranjero sigue debiendo el impuesto de trabajo por cuenta propia salvo que aplique un convenio de totalización; EE. UU. y México no tienen un convenio de totalización vigente (verificar)",
        "en": "a US citizen self-employed abroad still owes SE tax unless a totalization agreement applies; the US and Mexico have no totalization agreement in force (verify)",
    },
    # ------------------------------------------------------------------ crossborder/assessment.py
    "rules.xb.assessment.disclaimer": {
        "es": "Solo informativo. La residencia, la posición del tratado, el FBAR y la elección FEIE/FTC tienen consecuencias que Aurum no puede ver — llévalo a un preparador transfronterizo. Aurum no decide nada.",
        "en": "Informational only. Residency, treaty positions, FBAR and the FEIE/FTC choice all have consequences Aurum cannot see — take this to a cross-border preparer. Aurum decides nothing.",
    },
    "rules.xb.assessment.flag.fbar_required": {
        "es": "FBAR probablemente requerido — las cuentas extranjeras alcanzaron un máximo de {aggregate} USD, por encima del umbral de {threshold} USD (Formulario FinCEN 114, 31 C.F.R. 1010.350).",
        "en": "FBAR likely required — foreign accounts peaked at {aggregate} USD, above the {threshold} USD threshold (FinCEN Form 114, 31 C.F.R. 1010.350).",
    },
    "rules.xb.assessment.flag.fbar_not_required": {
        "es": "El FBAR no parece requerido con estos saldos, pero la prueba es el saldo más alto en cualquier día — revisa tus estados de cuenta, no tus cifras de fin de año.",
        "en": "FBAR does not look required on these balances, but the test is the highest balance on any single day — check your statements, not your year-end figures.",
    },
    "rules.xb.assessment.flag.dual_residency": {
        "es": "Posible doble residencia — desempate del tratado: el art. 4 del tratado EE. UU.-México decide qué país gana, y reclamarlo requiere el Formulario 8833. Explóralo con un preparador.",
        "en": "Possible dual residency — treaty tie-breaker: US-MX treaty art. 4 decides which country wins, and claiming it needs Form 8833. Explore with a preparer.",
    },
    "rules.xb.assessment.flag.us_resident": {
        "es": "Residente fiscal de EE. UU.: el ingreso mundial se reporta en el Formulario 1040.",
        "en": "US tax resident: worldwide income is reportable on Form 1040.",
    },
    "rules.xb.assessment.flag.mx_resident": {
        "es": "Residente fiscal de México: el ingreso mundial se reporta al SAT (CFF art. 9) (verificar).",
        "en": "Mexican tax resident: worldwide income is reportable to SAT (CFF art. 9) (verify).",
    },
    "rules.xb.assessment.flag.neither_resident": {
        "es": "Ninguna prueba apunta a residencia con estos datos — eso es inusual; confirma el conteo de días y dónde está tu casa.",
        "en": "Neither test points to residency on these facts — that is unusual; confirm the day counts and where your home is.",
    },
    "rules.xb.assessment.flag.feie_vs_ftc": {
        "es": "FEIE vs. FTC — explóralo con un preparador: hasta {available} USD podrían excluirse bajo IRC 911, o los {paid} USD de impuesto extranjero podrían acreditarse bajo IRC 901. Aurum no elige.",
        "en": "FEIE vs FTC — explore with a preparer: up to {available} USD could be excluded under IRC 911, or the {paid} USD of foreign tax could be credited under IRC 901. Aurum does not choose.",
    },
    "rules.xb.assessment.flag.feie_vs_ftc_neither": {
        "es": "FEIE vs. FTC — explóralo con un preparador: tienes ingreso ganado en el extranjero pero ni la prueba de 330 días ni la de residente de buena fe se cumplen con estos datos, así que el crédito fiscal extranjero es la vía a revisar.",
        "en": "FEIE vs FTC — explore with a preparer: you have foreign earned income but neither the 330-day nor the bona fide residence test is met on these facts, so the foreign tax credit is the path to look at.",
    },
    "rules.xb.assessment.flag.abroad_still_filing": {
        "es": "Vivir en el extranjero no termina la obligación de declarar en EE. UU. para un ciudadano o titular de tarjeta verde.",
        "en": "Living abroad does not end a US filing obligation for a citizen or green-card holder.",
    },
    "rules.xb.assessment.flag.no_accounts_recorded": {
        "es": "No hay cuentas extranjeras registradas — agrégalas si tienes alguna; el FBAR es fácil de pasar por alto.",
        "en": "No foreign accounts recorded — add them if you hold any; FBAR is easy to trip over.",
    },
    # ------------------------------------------------------------------ holdings/trades.py
    "holdings.positions.summary": {
        "es": "Las posiciones son lotes FIFO de las operaciones registradas; las ganancias realizadas emparejan las ventas con el lote abierto más antiguo (verificar contra la elección real de método de lote de tu jurisdicción).",
        "en": "Positions are FIFO lots from recorded trades; realized gains match sells to the oldest open lot first (verify against your jurisdiction's actual lot-method election).",
    },
    "holdings.tax_explain.mx.summary": {
        "es": "MX: las ganancias en valores mantenidos a través de un intermediario mexicano generalmente están sujetas a retención por el intermediario; el tratamiento de ganancias de capital personal depende del activo y la estructura de tenencia (verificar).",
        "en": "MX: gains on securities held through a Mexican broker are generally subject to withholding by the intermediary; personal capital-gains treatment depends on the asset and holding structure (verify).",
    },
    "holdings.tax_explain.us.summary": {
        "es": "US: las ganancias de capital a largo plazo (mantenidas > 1 año) reciben tasas preferentes; las ganancias a corto plazo se gravan como ingreso ordinario (verificar tasas/umbrales del año en curso).",
        "en": "US: long-term capital gains (held > 1 year) get preferential rates; short-term gains are taxed as ordinary income (verify current-year brackets/thresholds).",
    },
    # ------------------------------------------------------------------ creditreport/store.py
    "creditreport.score_factors.summary": {
        "es": "Factores que generalmente mueven un score de Buró de Crédito: historial de pagos, utilización de crédito, antigüedad/mezcla de crédito y consultas recientes (verificar contra el texto vigente de Buró/CONDUSEF).",
        "en": "Factors that generally move a Buró de Crédito score: payment history, credit utilization, credit age/mix, and recent inquiries (verify against current Buró/CONDUSEF text).",
    },
    "creditreport.score_factors.step.payment_history.label": {"es": "historial de pagos", "en": "payment_history"},
    "creditreport.score_factors.step.payment_history.value": {
        "es": "el factor individual más grande (verificar la ponderación exacta)",
        "en": "largest single factor (verify exact weighting)",
    },
    "creditreport.score_factors.step.utilization.label": {"es": "utilización", "en": "utilization"},
    "creditreport.score_factors.step.utilization.value": {
        "es": "una menor razón saldo-a-límite generalmente ayuda (verificar)",
        "en": "lower balance-to-limit ratio generally helps (verify)",
    },
    "creditreport.score_factors.step.credit_age_mix.label": {"es": "antigüedad_mezcla_de_crédito", "en": "credit_age_mix"},
    "creditreport.score_factors.step.credit_age_mix.value": {
        "es": "cuentas más antiguas y variadas generalmente ayudan (verificar)",
        "en": "older, varied accounts generally help (verify)",
    },
    "creditreport.score_factors.step.recent_inquiries.label": {"es": "consultas_recientes", "en": "recent_inquiries"},
    "creditreport.score_factors.step.recent_inquiries.value": {
        "es": "muchas consultas fuertes recientes pueden perjudicar (verificar)",
        "en": "many recent hard inquiries can hurt (verify)",
    },
    # ------------------------------------------------------------------ plan/scenarios/buy_vs_rent.py
    "plan.buy_vs_rent.summary": {
        "es": "A {years} años, comprar cuesta (VPN, incl. patrimonio recuperado) {buy} {currency} vs. rentar {rent} {currency}. Conviene {cheaper}.",
        "en": "Over {years} years, buying costs (NPV, incl. recovered equity) {buy} {currency} vs. renting {rent} {currency}. {cheaper} is cheaper.",
    },
    "plan.buy_vs_rent.cheaper.buy": {"es": "comprar", "en": "buying"},
    "plan.buy_vs_rent.cheaper.rent": {"es": "rentar", "en": "renting"},
    "plan.buy_vs_rent.step.down_payment": {"es": "Enganche", "en": "Down payment"},
    "plan.buy_vs_rent.step.monthly_mortgage": {"es": "Pago mensual de hipoteca", "en": "Monthly mortgage payment"},
    "plan.buy_vs_rent.step.home_value_horizon": {"es": "Valor de la vivienda al horizonte", "en": "Home value at the horizon"},
    "plan.buy_vs_rent.step.selling_costs": {"es": "Costos de venta estimados", "en": "Estimated selling costs"},
    "plan.buy_vs_rent.step.remaining_balance": {"es": "Saldo insoluto al horizonte", "en": "Remaining balance at the horizon"},
    "plan.buy_vs_rent.step.net_equity": {"es": "Patrimonio neto recuperado al vender", "en": "Net equity recovered on sale"},
    "plan.buy_vs_rent.step.buy_npv": {"es": "Costo neto (VPN) de comprar", "en": "Net (NPV) cost of buying"},
    "plan.buy_vs_rent.step.rent_npv": {"es": "Costo neto (VPN) de rentar", "en": "Net (NPV) cost of renting"},
    "plan.buy_vs_rent.step.breakeven_label": {
        "es": "Mes de equilibrio (comprar empieza a costar menos que rentar, acumulado y descontado)",
        "en": "Breakeven month (buying starts costing less than renting, cumulative and discounted)",
    },
    "plan.buy_vs_rent.breakeven.none": {"es": "no ocurre dentro del horizonte", "en": "does not occur within the horizon"},
    # ------------------------------------------------------------------ plan/scenarios/cash_vs_credit.py
    "plan.cash_vs_credit.summary": {
        "es": "Pagar de contado ({cash_price} con descuento) cuesta {cash_total} {currency} considerando el costo de oportunidad; financiar cuesta {credit_total} {currency} en intereses. Conviene {cheaper}.",
        "en": "Paying cash ({cash_price} with the discount) costs {cash_total} {currency} counting opportunity cost; financing costs {credit_total} {currency} in interest. {cheaper} is cheaper.",
    },
    "plan.cash_vs_credit.cheaper.cash": {"es": "de contado", "en": "cash"},
    "plan.cash_vs_credit.cheaper.credit": {"es": "a crédito", "en": "credit"},
    "plan.cash_vs_credit.step.list_price": {"es": "Precio de lista", "en": "List price"},
    "plan.cash_vs_credit.step.cash_price": {"es": "Precio de contado (con descuento)", "en": "Cash price (with discount)"},
    "plan.cash_vs_credit.step.opportunity_cost": {"es": "Costo de oportunidad del efectivo inmovilizado", "en": "Opportunity cost of tied-up cash"},
    "plan.cash_vs_credit.step.cash_total": {"es": "Costo total pagando de contado", "en": "Total cost paying cash"},
    "plan.cash_vs_credit.step.monthly_payment": {"es": "Pago mensual a crédito", "en": "Monthly credit payment"},
    "plan.cash_vs_credit.step.total_interest": {"es": "Interés total del crédito", "en": "Total credit interest"},
    "plan.cash_vs_credit.step.credit_total": {"es": "Costo total a crédito", "en": "Total cost on credit"},
    # ------------------------------------------------------------------ plan/scenarios/debt_payoff.py
    "plan.debt_payoff.summary": {
        "es": "Avalancha: {avalanche_months} meses, {avalanche_interest} {currency} de interés. Bola de nieve: {snowball_months} meses, {snowball_interest} {currency} de interés. Avalancha es matemáticamente ≤ en interés ({cheaper} gana en costo); bola de nieve puede motivar más por victorias tempranas.",
        "en": "Avalanche: {avalanche_months} months, {avalanche_interest} {currency} in interest. Snowball: {snowball_months} months, {snowball_interest} {currency} in interest. Avalanche is mathematically ≤ in interest ({cheaper} wins on cost); snowball can motivate more through early wins.",
    },
    "plan.debt_payoff.cheaper.avalanche": {"es": "avalancha", "en": "avalanche"},
    "plan.debt_payoff.cheaper.snowball": {"es": "bola de nieve", "en": "snowball"},
    "plan.debt_payoff.step.avalanche_order": {"es": "Orden avalancha (mayor tasa primero)", "en": "Avalanche order (highest rate first)"},
    "plan.debt_payoff.step.snowball_order": {"es": "Orden bola de nieve (menor saldo primero)", "en": "Snowball order (smallest balance first)"},
    "plan.debt_payoff.step.months_avalanche": {"es": "Meses libre de deuda — avalancha", "en": "Months debt-free — avalanche"},
    "plan.debt_payoff.step.months_snowball": {"es": "Meses libre de deuda — bola de nieve", "en": "Months debt-free — snowball"},
    "plan.debt_payoff.step.interest_avalanche": {"es": "Interés total — avalancha", "en": "Total interest — avalanche"},
    "plan.debt_payoff.step.interest_snowball": {"es": "Interés total — bola de nieve", "en": "Total interest — snowball"},
    "plan.debt_payoff.step.cheaper": {"es": "Más barato", "en": "Cheaper"},
    "plan.debt_payoff.step.faster": {"es": "Más rápido en liquidar la primera deuda", "en": "Faster to pay off the first debt"},
    # ------------------------------------------------------------------ plan/scenarios/entity_us.py
    "plan.entity_us.summary": {
        "es": "Comparación informativa (verify): sueldo-empleo por cuenta propia paga impuesto de autoempleo sobre todo el beneficio (~{sole_prop} {currency}); un S-corp con sueldo razonable de {salary} podría ahorrar ~{savings} {currency} en impuestos de nómina/autoempleo, a cambio de nómina, Form 1120-S y el riesgo de que el IRS impugne el sueldo por no ser 'razonable'.",
        "en": "Informational comparison (verify): self-employment income pays self-employment tax on the whole profit (~{sole_prop} {currency}); an S-corp with a reasonable salary of {salary} could save ~{savings} {currency} in payroll/self-employment tax, in exchange for payroll, Form 1120-S, and the risk of the IRS challenging the salary as not 'reasonable'.",
    },
    "plan.entity_us.step.net_profit": {"es": "Beneficio neto anual", "en": "Annual net profit"},
    "plan.entity_us.step.sole_prop_se_tax": {"es": "Sole proprietorship — impuesto de autoempleo", "en": "Sole proprietorship — self-employment tax"},
    "plan.entity_us.step.sole_prop_se_tax.formula": {
        "es": "92.35% × beneficio × ~15.3% (verify) = {value}",
        "en": "92.35% × profit × ~15.3% (verify) = {value}",
    },
    "plan.entity_us.step.llc_se_tax": {"es": "Single-member LLC (disregarded) — impuesto de autoempleo", "en": "Single-member LLC (disregarded) — self-employment tax"},
    "plan.entity_us.step.llc_se_tax.formula": {
        "es": "idéntico a sole proprietorship a nivel federal sin elección de entidad (verify)",
        "en": "identical to a sole proprietorship at the federal level absent an entity election (verify)",
    },
    "plan.entity_us.step.scorp_salary": {"es": "S-corp sketch — sueldo razonable", "en": "S-corp sketch — reasonable salary"},
    "plan.entity_us.step.scorp_distribution": {
        "es": "S-corp sketch — distribución (no sujeta a SE tax/FICA, verify)",
        "en": "S-corp sketch — distribution (not subject to SE tax/FICA, verify)",
    },
    "plan.entity_us.step.scorp_payroll_tax": {"es": "S-corp sketch — impuesto de nómina sobre el sueldo", "en": "S-corp sketch — payroll tax on the salary"},
    "plan.entity_us.step.scorp_savings": {"es": "Ahorro estimado del S-corp vs. sole prop/LLC", "en": "Estimated S-corp savings vs. sole prop/LLC"},
    "plan.entity_us.step.verify_label": {"es": "(verify)", "en": "(verify)"},
    "plan.entity_us.step.verify_note": {
        "es": "constantes de SE tax/FICA/umbral de Medicare adicional y elegibilidad S-corp no confirmadas en fuente primaria; 'sueldo razonable' está sujeto a escrutinio del IRS.",
        "en": "SE tax/FICA/additional-Medicare-threshold constants and S-corp eligibility have not been confirmed in a primary source; 'reasonable salary' is subject to IRS scrutiny.",
    },
    # ------------------------------------------------------------------ plan/scenarios/regime_mx.py
    "plan.regime_mx.summary": {
        "es": "RESICO: {resico} {currency} de ISR anual vs. Actividad Empresarial: {general} {currency}. Conviene {cheaper}.",
        "en": "RESICO: {resico} {currency} annual ISR vs. Business Activity regime: {general} {currency}. {cheaper} is cheaper.",
    },
    "plan.regime_mx.cheaper.resico": {"es": "RESICO", "en": "RESICO"},
    "plan.regime_mx.cheaper.general": {"es": "Actividad Empresarial", "en": "the Business Activity regime"},
    "plan.regime_mx.step.resico_isr": {"es": "ISR anual RESICO", "en": "Annual RESICO ISR"},
    "plan.regime_mx.step.general_isr": {"es": "ISR anual Actividad Empresarial", "en": "Annual Business Activity ISR"},
    "plan.regime_mx.step.resico_rate": {"es": "Tasa efectiva RESICO", "en": "RESICO effective rate"},
    "plan.regime_mx.step.general_rate": {"es": "Tasa efectiva Actividad Empresarial", "en": "Business Activity effective rate"},
    "plan.regime_mx.flip.never": {
        "es": "Ni con 95% de deducciones el régimen general resulta más barato en este nivel de ingreso.",
        "en": "Not even with 95% deductions does the general regime become cheaper at this income level.",
    },
    "plan.regime_mx.flip.always": {
        "es": "El régimen general ya conviene incluso sin deducciones a este nivel de ingreso.",
        "en": "The general regime is already cheaper even with no deductions at this income level.",
    },
    "plan.regime_mx.flip.ratio": {
        "es": "Si las deducciones autorizadas superan ~{pct}% del ingreso mensual, el régimen general se vuelve más barato que RESICO.",
        "en": "If authorized deductions exceed ~{pct}% of monthly income, the general regime becomes cheaper than RESICO.",
    },
    "plan.regime_mx.step.flip_label": {"es": "Qué voltearía la respuesta", "en": "What would flip the answer"},
    # ------------------------------------------------------------------ plan/scenarios/retirement.py
    "plan.retirement.summary": {
        "es": "A {years} años con {iterations} simulaciones (seed {seed}): saldo final p50 = {p50} {currency} (rango p10-p90: {p10} - {p90}).",
        "en": "Over {years} years with {iterations} simulations (seed {seed}): ending balance p50 = {p50} {currency} (p10-p90 range: {p10} - {p90}).",
    },
    "plan.retirement.step.starting_balance": {"es": "Saldo inicial", "en": "Starting balance"},
    "plan.retirement.step.monthly_contribution": {"es": "Aportación mensual (crece con inflación)", "en": "Monthly contribution (grows with inflation)"},
    "plan.retirement.step.expected_return": {"es": "Rendimiento esperado anual", "en": "Expected annual return"},
    "plan.retirement.step.volatility": {"es": "Volatilidad anual", "en": "Annual volatility"},
    "plan.retirement.step.p10": {"es": "p10 (escenario pesimista)", "en": "p10 (pessimistic scenario)"},
    "plan.retirement.step.p50": {"es": "p50 (mediana)", "en": "p50 (median)"},
    "plan.retirement.step.p90": {"es": "p90 (escenario optimista)", "en": "p90 (optimistic scenario)"},
    "plan.retirement.step.mean": {"es": "Media", "en": "Mean"},
    "plan.retirement.step.success_rate": {"es": "Tasa de éxito (nunca queda en negativo)", "en": "Success rate (balance never goes negative)"},
    # ------------------------------------------------------------------ business/invoices.py
    "business.invoices.register.summary": {
        "es": "Facturación: {issued} {currency} emitidos, {collected} cobrados, {outstanding} por cobrar al {as_of}. DSO {dso} días.",
        "en": "Invoicing: {issued} {currency} issued, {collected} collected, {outstanding} outstanding as of {as_of}. DSO {dso} days.",
    },
    "business.invoices.register.step.cfdi_issued": {"es": "CFDI emitidos tipo I", "en": "Type-I CFDIs issued"},
    "business.invoices.register.step.total_issued": {"es": "Total emitido", "en": "Total issued"},
    "business.invoices.register.step.collected": {"es": "Cobrado", "en": "Collected"},
    "business.invoices.register.step.collected_formula": {
        "es": "PUE en su fecha de emisión; PPD sólo con REP (imp_pagado)",
        "en": "PUE on its issue date; PPD only with a REP (imp_pagado)",
    },
    "business.invoices.register.step.outstanding": {"es": "Por cobrar", "en": "Outstanding"},
    "business.invoices.register.step.aging_bucket": {"es": "Antigüedad {bucket} días", "en": "Aging {bucket} days"},
    "business.invoices.register.step.aging_formula": {"es": "{count} factura(s)", "en": "{count} invoice(s)"},
    "business.invoices.register.step.dso": {"es": "DSO", "en": "DSO"},
    "business.invoices.dso.no_sales": {"es": "sin ventas en el periodo", "en": "no sales in the period"},
    # ------------------------------------------------------------------ business/payroll.py
    "business.payroll.employee.summary": {
        "es": "{name}: neto {net} {currency} = bruto {gross} − ISR {isr} − IMSS obrero {imss}.",
        "en": "{name}: net {net} {currency} = gross {gross} − ISR {isr} − employee IMSS {imss}.",
    },
    "business.payroll.employee.step.daily_salary": {"es": "Salario diario", "en": "Daily salary"},
    "business.payroll.employee.step.period_days": {"es": "Días del periodo", "en": "Days in the period"},
    "business.payroll.employee.step.gross": {"es": "Percepción bruta", "en": "Gross earnings"},
    "business.payroll.employee.step.isr_tarifa": {"es": "ISR tarifa art. 96", "en": "ISR tariff art. 96"},
    "business.payroll.employee.step.isr_tarifa_formula": {"es": "tasa marginal {rate}", "en": "marginal rate {rate}"},
    "business.payroll.employee.step.subsidy": {"es": "Subsidio para el empleo", "en": "Employment subsidy"},
    "business.payroll.employee.step.subsidy_unverified": {
        "es": "(verificar) — falta confirmarlo contra el decreto 2026",
        "en": "(verify) — not yet checked against the 2026 decree",
    },
    "business.payroll.employee.step.isr_retained": {"es": "ISR retenido", "en": "ISR withheld"},
    "business.payroll.employee.step.imss_employee": {"es": "Cuotas obreras IMSS", "en": "Employee IMSS quotas"},
    "business.payroll.employee.step.imss_employee_formula": {
        "es": "LSS arts. 25, 106 II, 107, 147, 168 II b)",
        "en": "LSS arts. 25, 106-II, 107, 147, 168-II-b",
    },
    "business.payroll.employee.step.sbc_daily": {"es": "SBC diario", "en": "Daily SBC"},
    "business.payroll.employee.step.sbc_capped": {"es": "topado a 25 UMA", "en": "capped at 25 UMA"},
    "business.payroll.employee.step.imss_employer": {"es": "Cuotas patronales IMSS", "en": "Employer IMSS quotas"},
    "business.payroll.employee.step.infonavit": {"es": "Aportación INFONAVIT", "en": "INFONAVIT contribution"},
    "business.payroll.employee.step.infonavit_formula": {
        "es": "5% (LINFONAVIT art. 29 fr. II)",
        "en": "5% (LINFONAVIT art. 29-II)",
    },
    "business.payroll.employee.step.net": {"es": "Neto a pagar", "en": "Net pay"},
    "business.payroll.run.summary": {
        "es": "Nómina {period}: costo patronal {employer_cost} {currency} para {headcount} empleado(s) — bruto {gross} + IMSS patronal {imss_employer} + INFONAVIT {infonavit} + ISN {isn}. Borrador, no es una declaración.",
        "en": "Payroll {period}: employer cost {employer_cost} {currency} for {headcount} employee(s) — gross {gross} + employer IMSS {imss_employer} + INFONAVIT {infonavit} + ISN {isn}. Draft, not a filing.",
    },
    "business.payroll.run.step.period_days": {"es": "Días del periodo", "en": "Days in the period"},
    "business.payroll.run.step.gross": {"es": "Percepciones brutas", "en": "Gross earnings"},
    "business.payroll.run.step.isr_retained": {"es": "ISR retenido a los trabajadores", "en": "ISR withheld from employees"},
    "business.payroll.run.step.imss_employee": {"es": "Cuotas obreras IMSS", "en": "Employee IMSS quotas"},
    "business.payroll.run.step.net": {"es": "Neto a pagar", "en": "Net pay"},
    "business.payroll.run.step.net_formula": {"es": "bruto − ISR − IMSS obrero", "en": "gross − ISR − employee IMSS"},
    "business.payroll.run.step.imss_employer": {"es": "Cuotas patronales IMSS", "en": "Employer IMSS quotas"},
    "business.payroll.run.step.infonavit": {"es": "Aportaciones INFONAVIT", "en": "INFONAVIT contributions"},
    "business.payroll.run.step.isn": {"es": "ISN Nuevo León", "en": "ISN Nuevo León"},
    "business.payroll.run.step.isn_formula": {"es": "3% sobre la base gravable (art. 157)", "en": "3% of the taxable base (art. 157)"},
    "business.payroll.run.step.employer_cost": {"es": "Costo patronal total", "en": "Total employer cost"},
    "business.payroll.run.step.employer_cost_formula": {
        "es": "bruto + IMSS patronal + INFONAVIT + ISN",
        "en": "gross + employer IMSS + INFONAVIT + ISN",
    },
    # ------------------------------------------------------------------ business/kpis.py
    "business.kpis.revenue.label": {"es": "Ingresos del periodo", "en": "Revenue for the period"},
    "business.kpis.revenue.step": {"es": "Suma de Income:* (signo invertido)", "en": "Sum of Income:* (sign inverted)"},
    "business.kpis.cogs.label": {"es": "Costo de ventas", "en": "Cost of goods sold"},
    "business.kpis.cogs.step": {"es": "Suma de Expenses:COGS:*", "en": "Sum of Expenses:COGS:*"},
    "business.kpis.gross_profit.label": {"es": "Utilidad bruta", "en": "Gross profit"},
    "business.kpis.gross_profit.step": {"es": "Ingresos − costo de ventas", "en": "Revenue − cost of goods sold"},
    "business.kpis.gross_margin.label": {"es": "Margen bruto", "en": "Gross margin"},
    "business.kpis.gross_margin.na": {"es": "n/d", "en": "n/a"},
    "business.kpis.gross_margin.step": {"es": "Utilidad bruta ÷ ingresos", "en": "Gross profit ÷ revenue"},
    "business.kpis.opex.summary": {
        "es": "Gastos de operación {total} {currency} (todo Expenses:* excepto COGS)",
        "en": "Operating expenses {total} {currency} (all Expenses:* except COGS)",
    },
    "business.kpis.opex.group_step": {"es": "Grupo · {name}", "en": "Group · {name}"},
    "business.kpis.operating_profit.label": {"es": "Utilidad de operación", "en": "Operating profit"},
    "business.kpis.operating_profit.step": {"es": "Utilidad bruta − gastos de operación", "en": "Gross profit − operating expenses"},
    "business.kpis.cash.label": {"es": "Efectivo y bancos", "en": "Cash and banks"},
    "business.kpis.cash.step": {"es": "Assets:Bank:* + Assets:Cash", "en": "Assets:Bank:* + Assets:Cash"},
    "business.kpis.receivables.label": {"es": "Cuentas por cobrar", "en": "Accounts receivable"},
    "business.kpis.receivables.step": {"es": "Assets:Receivable:*", "en": "Assets:Receivable:*"},
    "business.kpis.payables.label": {"es": "Cuentas por pagar", "en": "Accounts payable"},
    "business.kpis.payables.step": {"es": "Liabilities:Payable:*", "en": "Liabilities:Payable:*"},
    "business.kpis.runway.summary": {"es": "Runway {months} meses", "en": "Runway {months} months"},
    "business.kpis.runway.na": {"es": "Runway n/d — el negocio no está quemando efectivo", "en": "Runway n/a — the business is not burning cash"},
    "business.kpis.runway.step.cash": {"es": "Efectivo al cierre", "en": "Cash at close"},
    "business.kpis.runway.step.burn": {"es": "Quema promedio ({months} meses)", "en": "Average burn ({months} months)"},
    "business.kpis.runway.step.burn_formula": {
        "es": "gastos − ingresos, sólo meses con quema positiva",
        "en": "expenses − revenue, only months with positive burn",
    },
    "business.kpis.runway.step.months": {"es": "Meses de runway", "en": "Runway months"},
    "business.kpis.runway.na_value": {"es": "n/d", "en": "n/a"},
    "business.kpis.tax_reserve.warning_regime": {
        "es": "aurum.tax.month_close aplica reglas RESICO; el régimen declarado es {regime}. La reserva de ISR es una aproximación (verify).",
        "en": "aurum.tax.month_close applies RESICO rules; the declared regime is {regime}. The ISR reserve is an approximation (verify).",
    },
    "business.kpis.tax_reserve.step.isr_month_close": {"es": "ISR del mes (tax/month_close)", "en": "ISR for the month (tax/month_close)"},
    "business.kpis.tax_reserve.step.isr_formula": {"es": "regla mx.resico.isr_monthly", "en": "rule mx.resico.isr_monthly"},
    "business.kpis.tax_reserve.step.iva_month_close": {"es": "IVA a cargo (tax/month_close)", "en": "IVA payable (tax/month_close)"},
    "business.kpis.tax_reserve.step.iva_formula": {"es": "trasladado − acreditable", "en": "collected − creditable"},
    "business.kpis.tax_reserve.warning_no_tax_module": {
        "es": "aurum.tax no está instalado; la reserva usa saldos del libro mayor.",
        "en": "aurum.tax is not installed; the reserve uses ledger balances.",
    },
    "business.kpis.tax_reserve.warning_month_close_failed": {
        "es": "aurum.tax.month_close no pudo calcularse ({exc}); se usan saldos del libro.",
        "en": "aurum.tax.month_close could not be computed ({exc}); ledger balances are used.",
    },
    "business.kpis.tax_reserve.step.isr_payable": {"es": "ISR por pagar (Liabilities:Taxes:ISR*)", "en": "ISR payable (Liabilities:Taxes:ISR*)"},
    "business.kpis.tax_reserve.step.iva_payable": {"es": "IVA por pagar (Liabilities:Taxes:IVA*)", "en": "IVA payable (Liabilities:Taxes:IVA*)"},
    "business.kpis.tax_reserve.step.total": {"es": "Reserva fiscal total", "en": "Total tax reserve"},
    "business.kpis.tax_reserve.step.total_formula": {"es": "ISR + IVA", "en": "ISR + IVA"},
    "business.kpis.tax_reserve.summary": {
        "es": "Reserva fiscal sugerida {total} {currency} (fuente: {source})",
        "en": "Suggested tax reserve {total} {currency} (source: {source})",
    },
    "business.kpis.figure.summary": {"es": "{label}: {value} {currency}", "en": "{label}: {value} {currency}"},
    # ------------------------------------------------------------------ reports/packs.py
    "reports.monthly_review.overview": {"es": "Ingreso vs. gasto", "en": "Income vs. spend"},
    "reports.monthly_review.top_labels": {"es": "Principales categorías", "en": "Top labels"},
    "reports.monthly_review.anomalies": {"es": "Anomalías", "en": "Anomalies"},
    "reports.monthly_review.anomalies_note": {
        "es": "Una categoría que gasta más del doble de su promedio móvil de 3 meses.",
        "en": "A label spending more than 2x its trailing 3-month average.",
    },
    "reports.monthly_review.budgets": {"es": "Presupuestos", "en": "Budgets"},
    "reports.monthly_review.goals": {"es": "Metas", "en": "Goals"},
    "reports.monthly_review.upcoming_bills": {"es": "Próximos pagos", "en": "Upcoming due dates"},
    "reports.monthly_review.net_worth": {"es": "Patrimonio neto", "en": "Net worth"},
    "reports.mx_annual.summary": {"es": "Resumen {year}", "en": "{year} summary"},
    "reports.mx_annual.summary_note": {
        "es": "\"Calculado\" = lo que las reglas RESICO producen a partir del libro mayor cada mes. Aurum no rastrea lo realmente pagado al SAT — concilia contra tu estado de cuenta del SAT antes de declarar.",
        "en": "'Computed' = what the RESICO rules produce from the ledger each month. Aurum does not track what was actually paid to the SAT — reconcile against your SAT account statement (estado de cuenta) before filing.",
    },
    "reports.mx_annual.month_closes": {"es": "Cierres mensuales", "en": "Month closes"},
    "reports.mx_annual.deduction_candidates": {
        "es": "Candidatas a deducción personal (art. 151 LISR)",
        "en": "Personal deduction candidates (art. 151 LISR)",
    },
    "reports.mx_annual.deduction_note": {
        "es": "(verificar) Requiere CFDI + pago electrónico; confirma cada partida con tu contador.",
        "en": "(verify) Requires CFDI + electronic payment; confirm each item with your accountant.",
    },
    "reports.mx_annual.for_accountant": {"es": "Para tu contador", "en": "For your Contador"},
    "reports.mx_annual.note.confirm_ppd": {
        "es": "Confirma que cada CFDI emitido tenga su complemento de pago (PPD).",
        "en": "Confirm every emitted CFDI has its payment complement (PPD).",
    },
    "reports.mx_annual.note.review_deposits": {
        "es": "Revisa depósitos sin CFDI y facturas PUE no cobradas antes de declarar la anual.",
        "en": "Review deposits with no CFDI and uncollected PUE invoices before filing the annual return.",
    },
    "reports.mx_annual.note.gather_receipts": {
        "es": "Reúne comprobantes de deducciones personales candidatas (arriba) antes del 30 de abril.",
        "en": "Gather receipts for the personal-deduction candidates above before April 30.",
    },
    "reports.mx_annual.note.reconcile_withholding": {
        "es": "Coteja el ISR/IVA retenido de este reporte contra tus constancias de retención.",
        "en": "Reconcile the withheld ISR/IVA in this report against your retention certificates (constancias).",
    },
    "reports.us_organizer.schedule_c": {"es": "Anexo C (Schedule C)", "en": "Schedule C"},
    "reports.us_organizer.schedule_c_summary": {"es": "Resumen del Anexo C", "en": "Schedule C summary"},
    "reports.us_organizer.se_tax_estimates": {"es": "Impuesto de autoempleo y pagos estimados", "en": "SE tax & estimates"},
    "reports.us_organizer.se_tax_note": {
        "es": "Aurum no rastrea los pagos estimados realmente enviados al IRS/EFTPS — esta fila es el monto de refugio seguro calculado, no un saldo.",
        "en": "Aurum does not track estimated payments actually sent to the IRS/EFTPS — this row is the computed safe-harbor amount, not a balance.",
    },
    "reports.us_organizer.due_dates": {"es": "Fechas límite", "en": "Due dates"},
    "reports.us_organizer.tx_franchise": {"es": "Franquicia de Texas (verificación de no impuesto a pagar)", "en": "Texas franchise (no-tax-due check)"},
    "reports.us_organizer.crossborder": {"es": "Evaluación transfronteriza", "en": "Cross-border assessment"},
    "reports.us_organizer.fbar_accounts": {"es": "FBAR — cuentas extranjeras", "en": "FBAR — foreign accounts"},
    "reports.us_organizer.fbar_note": {
        "es": "Se requiere FBAR cuando el máximo agregado excede USD 10,000 en cualquier día.",
        "en": "FBAR required when the aggregate maximum exceeds USD 10,000 on any day.",
    },
    "reports.us_organizer.no_crossborder_profile": {
        "es": "No hay perfil transfronterizo en {ws_id} — primero haz PUT /api/crossborder/{ws_id}/profile.",
        "en": "No cross-border profile on {ws_id} — PUT /api/crossborder/{ws_id}/profile first.",
    },
    "reports.us_organizer.for_preparer": {"es": "Para tu preparador", "en": "For your preparer"},
    "reports.us_organizer.note.not_a_return": {
        "es": "Este organizador no es una declaración de impuestos. Aurum nunca presenta, firma ni transmite nada.",
        "en": "This organizer is not a tax return. Aurum never files, signs, or transmits anything.",
    },
    "reports.us_organizer.note.estimate_only": {
        "es": "Cada cifra es una estimación a partir del libro mayor — verifícala contra tus libros antes de declarar.",
        "en": "Every figure is an estimate from the ledger — verify against your books before filing.",
    },
    "reports.us_organizer.tax_position": {"es": "Posición fiscal", "en": "Tax position"},
    "reports.client_pack.exec_summary": {"es": "Resumen ejecutivo", "en": "Executive summary"},
    "reports.client_pack.statements_pnl": {"es": "Estados financieros — Estado de resultados", "en": "Statements — P&L"},
    "reports.client_pack.tax_position": {"es": "Posición fiscal", "en": "Tax position"},
    "reports.client_pack.open_items": {"es": "Pendientes", "en": "Open items"},
    "reports.client_pack.no_open_items": {"es": "Ninguno detectado este periodo.", "en": "None flagged this period."},
    "reports.net_worth.title": {"es": "Patrimonio neto", "en": "Net worth"},
    "reports.net_worth.series_12mo": {"es": "Serie de 12 meses", "en": "12-month series"},
    "reports.net_worth.holdings_positions": {"es": "Posiciones / Inversiones", "en": "Holdings / Positions"},
    "reports.error.title": {"es": "Error", "en": "Error"},
    # ------------------------------------------------------------------ insights (moved from aurum/insights/i18n.py)
    "insights.title.pue_not_collected": {"es": "Factura PUE sin cobrar", "en": "Uncollected PUE invoice"},
    "insights.title.ppd_missing_rep": {"es": "Factura PPD sin complemento", "en": "PPD invoice missing REP"},
    "insights.title.deposit_without_cfdi": {"es": "Depósito sin CFDI", "en": "Deposit without a CFDI"},
    "insights.title.cash_paid_expense": {"es": "Gasto pagado en efectivo", "en": "Cash-paid expense"},
    "insights.title.fixed_asset_iva": {"es": "IVA de activo fijo", "en": "Fixed-asset IVA"},
    "insights.title.you_may_owe": {"es": "Podrías deber ~{amount}", "en": "You may owe ~{amount}"},
    "insights.you_may_owe": {
        "es": "Con lo declarado hasta ahora podrías deber aproximadamente {amount} {currency} el {date}.",
        "en": "Based on what's booked so far, you may owe about {amount} {currency} by {date}.",
    },
    "insights.step_isr": {"es": "ISR", "en": "ISR"},
    "insights.step_iva": {"es": "IVA a pagar", "en": "IVA payable"},
    "insights.step_total": {"es": "Total estimado", "en": "Estimated total"},
    "insights.title.us_quarterly_estimate": {"es": "Pago trimestral US próximo", "en": "US quarterly estimate due soon"},
    "insights.us_quarterly_estimate": {
        "es": "El pago estimado trimestral de {amount} {currency} vence el {date}.",
        "en": "Your quarterly estimated payment of {amount} {currency} is due {date}.",
    },
    "insights.title.budget_alert": {"es": "Presupuesto de {name}", "en": "{name} budget"},
    "insights.budget_alert": {
        "es": "{name}: gastado {spent} de {budget} {currency} ({pct}%).",
        "en": "{name}: spent {spent} of {budget} {currency} ({pct}%).",
    },
    "insights.title.goal_off_track": {"es": "Meta '{name}' fuera de ritmo", "en": "Goal '{name}' off track"},
    "insights.goal_off_track": {
        "es": "El ritmo de ahorro reciente no alcanza lo que requiere la meta '{name}' cada mes.",
        "en": "Recent savings pace is below what goal '{name}' requires each month.",
    },
    "insights.step_monthly_required": {"es": "Aportación mensual requerida", "en": "Monthly required contribution"},
    "insights.step_recent_pace": {"es": "Ritmo reciente (promedio 3 meses)", "en": "Recent pace (3-month average)"},
    "insights.title.card_cut_due": {"es": "Corte de {name}", "en": "{name} statement cut"},
    "insights.card_cut_due": {
        "es": "La fecha de corte de {name} es el {date}.",
        "en": "{name}'s statement cut date is {date}.",
    },
    "insights.title.card_payment_due": {"es": "Pago de {name}", "en": "{name} payment due"},
    "insights.card_payment_due": {
        "es": "El pago de {name} vence el {date}.",
        "en": "{name}'s payment is due {date}.",
    },
    "insights.title.recurring_bill_due": {"es": "Cargo recurrente: {name}", "en": "Recurring bill: {name}"},
    "insights.recurring_bill_due": {
        "es": "Se espera el cargo recurrente de {name} el {date}.",
        "en": "The recurring charge from {name} is expected on {date}.",
    },
    "insights.title.spending_anomaly": {"es": "Gasto atípico en {name}", "en": "Spending anomaly in {name}"},
    "insights.anomaly": {
        "es": "El gasto en {name} este mes es {ratio}x su promedio trimestral.",
        "en": "Spend on {name} this month is {ratio}x its trailing quarterly average.",
    },
    "insights.step_amount": {"es": "Monto del mes", "en": "This month's amount"},
    "insights.step_trailing_average": {"es": "Promedio trimestral", "en": "Trailing 3-month average"},
    "insights.title.regime_exit_risk": {"es": "Riesgo de salida de RESICO", "en": "RESICO regime-exit risk"},
    "insights.regime_exit_risk": {
        "es": (
            "Al ritmo actual tu ingreso anualizado alcanza {pct}% del tope de RESICO ({cap} {currency}); "
            "superarlo te saca del régimen el mes siguiente (LISR art. 113-E, verificar redacción exacta)."
        ),
        "en": (
            "At the current pace, your annualized income reaches {pct}% of the RESICO cap ({cap} {currency}); "
            "exceeding it moves you out of the regime the following month (LISR art. 113-E, verify exact wording)."
        ),
    },
    "insights.step_ytd_income": {"es": "Ingreso acumulado del año", "en": "Year-to-date income"},
    "insights.step_annualized": {"es": "Ingreso anualizado", "en": "Annualized income"},
    "insights.step_cap": {"es": "Tope anual RESICO", "en": "RESICO annual cap"},
    "insights.title.missing_statement": {"es": "Falta estado de cuenta", "en": "Missing bank statement"},
    "insights.missing_statement": {
        "es": "No hay movimientos bancarios registrados para {period}; sube el estado de cuenta del período.",
        "en": "No bank postings found for {period}; upload that period's bank statement.",
    },
    "insights.action.view_month_close": {"es": "Ver cierre del mes", "en": "View month close"},
    "insights.action.view_us_tax": {"es": "Ver impuestos US", "en": "View US tax"},
    "insights.action.view_budgets": {"es": "Ver presupuestos", "en": "View budgets"},
    "insights.action.view_goals": {"es": "Ver metas", "en": "View goals"},
    "insights.action.view_credit": {"es": "Ver tarjetas", "en": "View cards"},
    "insights.action.view_recurring": {"es": "Ver recurrentes", "en": "View recurring"},
    "insights.action.view_review": {"es": "Ver revisión mensual", "en": "View monthly review"},
    "insights.action.upload_statement": {"es": "Subir estado de cuenta", "en": "Upload statement"},
    "insights.digest.title": {"es": "Resumen de Aurum", "en": "Aurum digest"},
    "insights.digest.none": {"es": "Sin novedades para {period}.", "en": "Nothing new for {period}."},
    "insights.digest.urgent_count": {
        "es": "{count} urgente(s), {warn} de atención, {info} informativo(s).",
        "en": "{count} urgent, {warn} to watch, {info} informational.",
    },
    "insights.telegram.quickadd_ok": {
        "es": "Anotado: {text}\nRevísalo en Aurum cuando puedas.",
        "en": "Noted: {text}\nCheck your Aurum inbox.",
    },
    "insights.telegram.quickadd_error": {
        "es": "No pude leer eso como un movimiento ({error}). Intenta: '250 tacos comida'.",
        "en": "I couldn't parse that as a transaction ({error}). Try: '250 tacos comida'.",
    },
    "insights.telegram.unknown_chat": {
        "es": "Este chat no está vinculado a ningún workspace de Aurum. Pide al operador que agregue tu chat_id a AURUM_TELEGRAM_WS_MAP.",
        "en": "This chat isn't linked to any Aurum workspace. Ask the operator to add your chat_id to AURUM_TELEGRAM_WS_MAP.",
    },
    "insights.telegram.photo_ack": {
        "es": "Recibí tu foto. Aún no proceso OCR aquí; súbela desde la app en Documentos.",
        "en": "Got your photo. OCR isn't wired up here yet; upload it from the Documents screen instead.",
    },
    # --- organizer ("Mi dinero" money organizer) -------------------------------------------------
    "organizer.commitment": {
        "es": "{name}: pago fijo con cadencia {cadence}; el equivalente mensual normaliza el monto a un mes.",
        "en": "{name}: commitment with {cadence} cadence; the monthly equivalent normalizes the amount to one month.",
    },
    "organizer.summary": {
        "es": "Pagos fijos al mes = suma de cada pago fijo activo llevado a su equivalente mensual.",
        "en": "Committed per month = every active commitment converted to its monthly equivalent.",
    },
    "organizer.detect": {
        "es": (
            "Detección determinista: se normaliza el comercio, se agrupan cargos con monto similar (±10%) "
            "y la cadencia sale de la mediana de los intervalos."
        ),
        "en": (
            "Deterministic detection: the merchant is normalized, charges within ±10% are grouped, and the "
            "cadence comes from the median interval."
        ),
    },
    "organizer.detect.candidate": {
        "es": "{merchant}: {count} cargos, intervalos {intervals} días (mediana {median}) → {cadence}.",
        "en": "{merchant}: {count} charges, intervals {intervals} days (median {median}) → {cadence}.",
    },
    "organizer.safe_to_spend": {
        "es": (
            "Lo que tienes en banco y efectivo, menos los pagos fijos que faltan, lo que te queda por gastar "
            "de tu presupuesto y un pequeño colchón por si algo se atrasa."
        ),
        "en": (
            "What you have in bank and cash, minus the fixed payments still to come, what is left to spend in "
            "your budget and a small cushion in case something runs late."
        ),
    },
    "organizer.forecast": {
        "es": (
            "Lo que tienes hoy, más los ingresos que esperas y menos los pagos fijos que vienen, día por día. "
            "Es una suma simple, no una predicción."
        ),
        "en": (
            "What you have today, plus the income you expect and minus the fixed payments coming up, day "
            "by day. It is a simple sum, not a prediction."
        ),
    },
    "organizer.calendar": {
        "es": (
            "Calendario: ocurrencias proyectadas, cortes y pagos de tarjeta, préstamos e ingresos. "
            "Una ocurrencia se marca pagada si hay un movimiento en ±3 días y ±10% del monto."
        ),
        "en": (
            "Calendar: projected occurrences, card cut/due dates, loans and income. An occurrence counts "
            "as paid when a ledger transaction falls within ±3 days and ±10% of the amount."
        ),
    },
    "organizer.plan": {
        "es": "Plan por sobres: Necesidades / Gustos / Ahorro / Deuda, planeado vs. real del período.",
        "en": "Envelope plan: Needs / Wants / Savings / Debt, planned vs. actual for the period.",
    },
    "organizer.plan.auto": {
        "es": "Propuesta = promedio de los últimos {months} meses por categoría, con piso en los pagos fijos activos.",
        "en": "Proposal = average of the last {months} months per label, floored at the active commitments.",
    },
    "organizer.quickadd": {
        "es": "Texto interpretado con reglas ES/EN (sin modelo): monto, cadencia, día, moneda y prueba.",
        "en": "Text parsed with ES/EN rules (no model): amount, cadence, day, currency and trial.",
    },
    "organizer.setup": {
        "es": "Configuración en 3 pasos: movimientos bancarios → pagos fijos detectados → plan.",
        "en": "Three-step setup: bank lines → detected commitments → plan.",
    },
    "organizer.organize": {
        "es": "Recategorización de movimientos; con `create_rule` el comercio queda como alias de la categoría.",
        "en": "Transactions relabeled; with `create_rule` the merchant becomes an alias of the label.",
    },
    "organizer.alert.title.price_increase": {"es": "Subió el precio: {name}", "en": "Price increase: {name}"},
    "organizer.alert.price_increase": {
        "es": "{name} pasó de {old} a {new} ({pct}%).",
        "en": "{name} went from {old} to {new} ({pct}%).",
    },
    "organizer.alert.title.price_decrease": {"es": "Bajó el precio: {name}", "en": "Price decrease: {name}"},
    "organizer.alert.price_decrease": {
        "es": "{name} bajó de {old} a {new} ({pct}%).",
        "en": "{name} dropped from {old} to {new} ({pct}%).",
    },
    "organizer.alert.title.trial_ending": {"es": "Termina la prueba: {name}", "en": "Trial ending: {name}"},
    "organizer.alert.trial_ending": {
        "es": "La prueba de {name} termina el {date}; después se cobrarán {amount}.",
        "en": "The {name} trial ends on {date}; after that it charges {amount}.",
    },
    "organizer.alert.title.missed_payment": {"es": "Pago no detectado: {name}", "en": "Payment not seen: {name}"},
    "organizer.alert.missed_payment": {
        "es": "{name} vencía el {date} ({amount}) y no se encontró un movimiento que lo cubra.",
        "en": "{name} was due on {date} ({amount}) and no matching movement was found.",
    },
    "organizer.alert.title.upcoming": {"es": "Próximo cargo: {name}", "en": "Upcoming charge: {name}"},
    "organizer.alert.upcoming": {
        "es": "{name} se cobra el {date} por {amount}.",
        "en": "{name} charges on {date} for {amount}.",
    },
    "organizer.alert.title.duplicate": {"es": "Servicios duplicados", "en": "Duplicate services"},
    "organizer.alert.duplicate": {
        "es": "{names} son del mismo tipo ({hint}); juntos cuestan {amount} al mes.",
        "en": "{names} are the same type ({hint}); together they cost {amount} a month.",
    },
    "organizer.alert.title.annual_renewal": {"es": "Renovación anual: {name}", "en": "Annual renewal: {name}"},
    "organizer.alert.annual_renewal": {
        "es": "{name} se renueva el {date} por {amount}.",
        "en": "{name} renews on {date} for {amount}.",
    },
    "organizer.alert.title.forgotten": {"es": "Sin revisar: {name}", "en": "Unreviewed: {name}"},
    "organizer.alert.forgotten": {
        "es": "{name} lleva {months} meses sin revisarse; confirma que sigues usándolo.",
        "en": "{name} has gone {months} months without a review; confirm you still use it.",
    },
    "pf.entry.expense": {"es": "Gasto", "en": "Expense"},
    "pf.entry.income": {"es": "Ingreso", "en": "Income"},
    "pf.entry.transfer": {"es": "Transferencia", "en": "Transfer"},
    "pf.entry.external_source": {
        "es": "Creado por otro proceso (origen: {source}); edítalo desde ahí para no alterar una cifra fiscal.",
        "en": "Created by another process (source: {source}); edit it there so a tax figure stays intact.",
    },
    "pf.stream.income": {
        "es": "Ingreso recurrente: {name}, {cadence}.",
        "en": "Recurring income: {name}, {cadence}.",
    },
    "pf.onboarding": {
        "es": "Progreso de configuración inicial: cuentas, ingresos, pagos fijos y categorías.",
        "en": "Setup progress: accounts, income, recurring bills and categories.",
    },
    "pf.onboarding.accounts": {
        "es": "Agrega al menos una cuenta (banco, efectivo o tarjeta) para empezar a registrar movimientos.",
        "en": "Add at least one account (bank, cash or card) to start logging movements.",
    },
    "pf.onboarding.income": {
        "es": "Configura de dónde viene tu dinero: sueldo, freelance, renta u otro ingreso recurrente.",
        "en": "Set up where your money comes from: salary, freelance, rent or another recurring income.",
    },
    "pf.onboarding.recurring": {
        "es": "Agrega tus pagos fijos (renta, suscripciones, servicios) para verlos en el calendario.",
        "en": "Add your recurring bills (rent, subscriptions, utilities) to see them on the calendar.",
    },
    "pf.onboarding.categories": {
        "es": "Tus categorías ya están listas; edítalas si quieres ajustarlas a tus gastos.",
        "en": "Your categories are ready; edit them if you want to fit your own spending.",
    },
    "pf.onboarding.import": {
        "es": "Opcional: importa tu estado de cuenta para no capturar todo a mano.",
        "en": "Optional: import your bank statement so you don't have to type everything by hand.",
    },
    # --- pf keys ---
    "pf.entry.label_kind_mismatch": {
        "es": "Esa categoría es de {kind}; elige una de {expected}.",
        "en": "That category is for {kind}; pick one for {expected}.",
    },
    "pf.entry.kind_plural.expense": {"es": "gastos", "en": "expenses"},
    "pf.entry.kind_plural.income": {"es": "ingresos", "en": "income"},
    "pf.entry.kind_plural.transfer": {"es": "transferencias", "en": "transfers"},
    "pf.entry.voided": {"es": "Este movimiento fue eliminado.", "en": "This movement was deleted."},
    "pf.budget_status_all": {
        "es": "Cuánto llevas gastado y cuánto te queda en cada categoría del mes.",
        "en": "How much you have spent and how much is left in each category for the month.",
    },
    "pf.onboarding.first_entries": {
        "es": "Registra tu primer movimiento (un café basta) para ver cómo cambia tu saldo.",
        "en": "Log your first movement (a coffee is enough) to see your balance change.",
    },
    # Receipt photos (aurum/ingest/receipts.py)
    "receipt.err.empty": {"es": "El archivo llegó vacío.", "en": "The file arrived empty."},
    "receipt.err.type": {
        "es": "Eso no parece una foto. Sube una imagen JPG, PNG o WebP.",
        "en": "That does not look like a photo. Upload a JPG, PNG or WebP image.",
    },
    "receipt.err.heic": {
        "es": "Las fotos HEIC del iPhone no se pueden leer aún. En Ajustes › Cámara › Formatos elige «Más compatible», o envíala como JPG.",
        "en": "iPhone HEIC photos can't be read yet. In Settings › Camera › Formats pick “Most Compatible”, or send it as a JPG.",
    },
    "receipt.msg.ocr_off": {
        "es": "Guardamos la foto. Este equipo no tiene lector de texto instalado, así que escribe el monto a mano.",
        "en": "Photo saved. This machine has no text reader installed, so type the amount by hand.",
    },
    "receipt.msg.ocr_failed": {
        "es": "Guardamos la foto, pero no pudimos leerla (puede estar borrosa u oscura). Escribe el monto a mano.",
        "en": "Photo saved, but we couldn't read it (it may be blurry or dark). Type the amount by hand.",
    },
    "receipt.msg.no_total": {
        "es": "Leímos el recibo, pero no encontramos el total. Escríbelo a mano.",
        "en": "We read the receipt but couldn't find the total. Type it by hand.",
    },
    "receipt.why.amount.line": {"es": "Monto: la línea «{line}».", "en": "Amount: the line “{line}”."},
    "receipt.why.amount.card": {
        "es": "Monto: el cobro a la tarjeta, «{line}».",
        "en": "Amount: the card charge, “{line}”.",
    },
    "receipt.why.amount.largest": {
        "es": "Monto: no vimos la palabra TOTAL; es la cifra más grande del ticket («{line}»). Revísalo.",
        "en": "Amount: no TOTAL line; it's the largest figure on the ticket (“{line}”). Check it.",
    },
    "receipt.why.check.subtotal_iva": {
        "es": "Cuadra con el subtotal más el IVA.",
        "en": "It matches the subtotal plus tax.",
    },
    "receipt.why.check.card_match": {
        "es": "Coincide con lo que se cobró a la tarjeta.",
        "en": "It matches what was charged to the card.",
    },
    "receipt.why.date": {"es": "Fecha: «{line}».", "en": "Date: “{line}”."},
    "receipt.why.merchant.known": {"es": "Comercio: {name} (lo reconocemos).", "en": "Shop: {name} (we know it)."},
    "receipt.why.merchant.header": {
        "es": "Comercio: el nombre al inicio del ticket, «{name}».",
        "en": "Shop: the name at the top of the ticket, “{name}”.",
    },
    "receipt.why.cat.learned": {
        "es": "Categoría: {label}, como la última vez que registraste {payee}.",
        "en": "Category: {label}, like the last time you logged {payee}.",
    },
    "receipt.why.cat.merchant": {
        "es": "Categoría: {label}, porque es {name}.",
        "en": "Category: {label}, because it's {name}.",
    },
    "receipt.why.cat.words": {
        "es": "Categoría: {label}, por las palabras {words}.",
        "en": "Category: {label}, from the words {words}.",
    },
    "receipt.why.cat.alias": {
        "es": "Categoría: {label}, por el nombre del comercio.",
        "en": "Category: {label}, from the shop's name.",
    },
    "pf.quickadd.no_account": {
        "es": "Primero agrega una cuenta para registrar movimientos.",
        "en": "Add an account first so movements have somewhere to land.",
    },
    "pf.quickadd.label_kind_dropped": {
        "es": "La categoría {label} es de {kind}; se dejó sin categoría.",
        "en": "Category {label} is for {kind}; left uncategorized.",
    },
    "pf.quickadd.no_label": {
        "es": "No se encontró una categoría; puedes elegirla al guardar.",
        "en": "No category matched; you can pick one when saving.",
    },
    # --- end pf keys ---
    # --- organizer alerts and setup keys ---
    "organizer.alert.title.income_expected": {"es": "Ingreso esperado: {name}", "en": "Income expected: {name}"},
    "organizer.alert.income_expected": {
        "es": "{name} debería llegar el {date} por {amount}.",
        "en": "{name} should arrive on {date} for {amount}.",
    },
    "organizer.alert.title.income_late": {"es": "Ingreso atrasado: {name}", "en": "Income late: {name}"},
    "organizer.alert.income_late": {
        "es": "{name} se esperaba el {date} ({amount}) y todavía no aparece un depósito.",
        "en": "{name} was expected on {date} ({amount}) and no deposit has shown up yet.",
    },
    "organizer.alert.title.income_changed": {"es": "Cambió el ingreso: {name}", "en": "Income changed: {name}"},
    "organizer.alert.income_changed": {
        "es": "{name} pasó de {old} a {new} ({pct}%).",
        "en": "{name} went from {old} to {new} ({pct}%).",
    },
    "organizer.alert.title.cancelled_still_charging": {
        "es": "Sigue cobrando: {name}",
        "en": "Still charging: {name}",
    },
    "organizer.alert.cancelled_still_charging": {
        "es": "{name} está cancelado pero volvió a cobrar {amount} el {date}. Revisa el cargo.",
        "en": "{name} is cancelled but charged {amount} again on {date}. Check the charge.",
    },
    "organizer.quickadd.no_amount": {
        "es": "Falta el monto (p. ej. \"netflix 219 mensual\")",
        "en": "Missing the amount (e.g. \"netflix 219 monthly\")",
    },
    "organizer.step.liquid_balance": {
        "es": "Lo que tienes en tus cuentas de banco y en efectivo, sin contar tus ahorros",
        "en": "What you have in your bank and cash accounts, not counting your savings",
    },
    "organizer.step.until_income": {
        "es": "Hasta tu próximo ingreso, el {date}",
        "en": "Until your next income, on {date}",
    },
    "organizer.step.until_default": {
        "es": "Sin ingresos registrados: {days} días a partir de hoy",
        "en": "No income set up: {days} days from today",
    },
    "organizer.step.committed_until": {
        "es": "Pagos fijos pendientes hasta el {date}: {items}",
        "en": "Fixed payments still pending until {date}: {items}",
    },
    "organizer.step.budgeted_remaining": {
        "es": "Lo que falta por gastar de tus presupuestos este mes: {items}",
        "en": "What is left to spend in this month's budgets: {items}",
    },
    "organizer.step.buffer_explicit": {
        "es": "Colchón que definiste en Mi dinero",
        "en": "Buffer you set in Mi dinero",
    },
    "organizer.step.buffer_default": {
        "es": "Colchón automático: 10 % de tus pagos fijos mensuales",
        "en": "Automatic buffer: 10 % of your monthly fixed payments",
    },
    "organizer.step.safe_to_spend": {
        "es": "{balance} − {fixed} pagos fijos − {budgets} presupuestos − {buffer} colchón",
        "en": "{balance} − {fixed} fixed payments − {budgets} budgets − {buffer} buffer",
    },
    "organizer.step.none": {"es": "ninguno", "en": "none"},
    "organizer.step.income_expected": {
        "es": "Ingresos fijos llevados a su equivalente mensual",
        "en": "Fixed income at its monthly equivalent",
    },
    "organizer.step.income_actual": {
        "es": "Ingresos registrados en el período",
        "en": "Income logged in the period",
    },
    "organizer.step.total_actual": {
        "es": "Gastado según los cuatro sobres (cada pago fijo contado una vez)",
        "en": "Spent across the four envelopes (each fixed payment counted once)",
    },
    "organizer.step.expenses_actual": {
        "es": "Todos los gastos registrados en el período",
        "en": "Every expense logged in the period",
    },
    "organizer.step.savings_rate": {
        "es": "(ingresos − gastos) ÷ ingresos",
        "en": "(income − expenses) ÷ income",
    },
    "insights.action.view_organizer": {"es": "Ver Mi dinero", "en": "Open Mi dinero"},
    # --- end organizer alerts and setup keys ---
}


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    """Look up ``key`` in ``lang`` (default ``es``), falling back to ``es`` then the raw key."""
    resolved: Lang = "en" if (lang or "").lower().startswith("en") else _DEFAULT
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(resolved) or entry.get(_DEFAULT) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


_MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_CURRENCY_PREFIX = {"USD": "US$", "MXN": "MX$"}


def fmt_money(amount, currency: str, lang: str | None = None, base_currency: str | None = None) -> str:
    """Human money for prose, the server-side twin of the UI's money format: the workspace base
    currency renders as ``$``, USD/MXN as ``US$``/``MX$``, anything else as ``EUR 1,234.56``; thousands
    separated, two decimals, negatives with U+2212. No locale calls — the same string on every machine."""
    from decimal import ROUND_HALF_UP, Decimal

    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "\u2212" if value < 0 else ""
    digits = f"{abs(value):,.2f}"
    code = (currency or "").upper()
    if base_currency and code == base_currency.upper():
        return f"{sign}${digits}"
    prefix = _CURRENCY_PREFIX.get(code)
    if prefix:
        return f"{sign}{prefix}{digits}"
    return f"{sign}{code} {digits}".strip()


def fmt_date(d, lang: str | None = None) -> str:
    """``12 sep 2026`` (es) / ``Sep 12, 2026`` (en); accepts a date or an ISO string."""
    from datetime import date as _date

    if isinstance(d, str):
        d = _date.fromisoformat(d[:10])
    resolved: Lang = "en" if (lang or "").lower().startswith("en") else _DEFAULT
    if resolved == "en":
        return f"{_MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{d.day} {_MONTHS_ES[d.month - 1]} {d.year}"


def resolve_lang(explicit: str | None, workspace_language: str | None) -> str:
    """``?lang=`` wins when given; otherwise the workspace's language; otherwise ``es``."""
    if explicit:
        return "en" if explicit.lower().startswith("en") else "es"
    return "en" if (workspace_language or "").lower().startswith("en") else "es"


def ws_lang(ws_id: str, explicit: str | None = None) -> str:
    """``?lang=`` wins when given; otherwise ``Workspace.language``; otherwise ``es``.

    Looks the workspace up defensively — an unknown workspace (e.g. mid-test-fixture) falls back
    to ``es`` rather than raising, since callers use this purely to pick summary text.
    """
    if explicit:
        return "en" if explicit.lower().startswith("en") else "es"
    try:
        from .workspaces import WorkspaceNotFound, get_workspace

        return resolve_lang(None, get_workspace(ws_id).language)
    except WorkspaceNotFound:
        return _DEFAULT
