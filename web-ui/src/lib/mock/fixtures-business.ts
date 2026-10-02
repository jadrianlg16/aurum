/**
 * Mock fixtures for business / insights / reports and workflows.
 *
 * The business, insights and reports shapes are copied from the *real* responses recorded in
 * `web-ui/docs/api-samples.json` (workspaces `demo-biz` and `demo-mx`), with the arrays the
 * capture truncated filled back in so the screens have something to render. The workflow
 * fixtures follow the real `/api/workflows` shapes (verified 2026-09): a bare summary list,
 * a per-workflow detail with `yaml` + parsed `definition`, and run traces with per-step
 * HTTP status/duration.
 *
 * Money discipline: every amount below is a decimal *string*. The payroll totals were summed
 * with exact decimal arithmetic before being written down; the mock never adds money at run
 * time.
 */
import type {
  ArchivedReport,
  BizConstants,
  BusinessKpis,
  CalendarEntry,
  Employee,
  Insight,
  InvoiceRegister,
  PayrollLine,
  PayrollRun,
  PayrollRunSummary,
  ReportPack,
  ReportPreview,
  WorkflowCatalog,
  WorkflowDefinition,
  Workspace,
} from '../types';

export const BIZ_WS_ID = 'demo-biz';
const MXN = 'MXN';
const amt = (amount: string) => ({ amount, currency: MXN });
const explain = (
  summary: string,
  steps: { label: string; formula?: string | null; value: string }[] = [],
  rule_versions: string[] = [],
) => ({
  summary,
  steps: steps.map((s) => ({ label: s.label, formula: s.formula ?? null, value: s.value })),
  citations: [],
  rule_versions,
  confidence: null,
});

/** The third demo workspace (`demo-biz`): persona moral in Nuevo León. */
export const BIZ_WORKSPACE: Workspace = {
  id: BIZ_WS_ID,
  name: 'Demo Negocio (persona moral, NL)',
  kind: 'business',
  jurisdictions: ['MX'],
  base_currency: MXN,
  language: 'es',
  profile: { rfc: '*********1AA1', regime: 'GENERAL_PM', state: 'NL', country: 'MX', demo: true },
  created_at: '2026-09-06T23:30:00.000000Z',
};

/* --------------------------------------------------------------------- KPIs */

export function bizKpis(period: string): BusinessKpis {
  return {
    workspace: BIZ_WS_ID,
    period,
    currency: MXN,
    revenue: {
      ...amt('256000.00'),
      explain: explain('Ingresos del periodo: 256000.00 MXN', [
        { label: 'Suma de Income:* (signo invertido)', value: '256000.00' },
      ]),
    },
    cogs: {
      ...amt('68500.00'),
      explain: explain('Costo de ventas: 68500.00 MXN', [
        { label: 'Suma de Expenses:COGS:*', value: '68500.00' },
      ]),
    },
    gross_profit: {
      ...amt('187500.00'),
      explain: explain('Utilidad bruta: 187500.00 MXN', [
        { label: 'Ingresos − costo de ventas', formula: '256000.00 − 68500.00', value: '187500.00' },
      ]),
    },
    gross_margin: {
      value: '0.7324',
      percent: '73.24',
      explain: explain('Margen bruto 73.24%', [
        { label: 'Utilidad bruta ÷ ingresos', formula: '187500.00 ÷ 256000.00', value: '0.7324' },
      ]),
    },
    operating_expenses: {
      total: amt('121827.12'),
      by_group: [
        { group: 'Payroll', amount: amt('69327.12') },
        { group: 'Rent', amount: amt('28000.00') },
        { group: 'Marketing', amount: amt('15000.00') },
        { group: 'Software', amount: amt('9500.00') },
      ],
      payroll: amt('69327.12'),
      explain: explain('Gastos de operación 121827.12 MXN (todo Expenses:* excepto COGS)', [
        { label: 'Grupo · Payroll', value: '69327.12' },
        { label: 'Grupo · Rent', value: '28000.00' },
        { label: 'Grupo · Marketing', value: '15000.00' },
        { label: 'Grupo · Software', value: '9500.00' },
      ]),
    },
    operating_profit: {
      ...amt('65672.88'),
      explain: explain('Utilidad de operación: 65672.88 MXN', [
        {
          label: 'Utilidad bruta − gastos de operación',
          formula: '187500.00 − 121827.12',
          value: '65672.88',
        },
      ]),
    },
    cash: {
      ...amt('474940.00'),
      explain: explain('Efectivo y bancos: 474940.00 MXN', [
        { label: 'Assets:Bank:* + Assets:Cash', value: '474940.00' },
      ]),
    },
    receivables: {
      ...amt('315520.00'),
      explain: explain('Cuentas por cobrar: 315520.00 MXN', [
        { label: 'Assets:Receivable:*', value: '315520.00' },
      ]),
    },
    payables: {
      ...amt('86400.00'),
      explain: explain('Cuentas por pagar: 86400.00 MXN', [
        { label: 'Liabilities:Payable:*', value: '86400.00' },
      ]),
    },
    runway: {
      months: '3.9',
      average_burn: amt('121827.12'),
      lookback_months: 3,
      explain: explain('Efectivo ÷ quema promedio de 3 meses = 3.9 meses', [
        { label: 'Efectivo', value: '474940.00' },
        { label: 'Quema promedio (3 meses)', value: '121827.12' },
        { label: 'Runway', formula: '474940.00 ÷ 121827.12', value: '3.9' },
      ]),
    },
    tax_reserve: {
      total: amt('48320.00'),
      isr: amt('19702.00'),
      iva: amt('28618.00'),
      source: 'ledger',
      warnings: [
        'aurum.tax.month_close aplica reglas RESICO; el régimen declarado es GENERAL_PM. La reserva de ISR es una aproximación (verify).',
      ],
      explain: explain('Reserva fiscal sugerida 48320.00 MXN (fuente: ledger)', [
        { label: 'ISR por pagar (Liabilities:Taxes:ISR*)', value: '19702.00' },
        { label: 'IVA por pagar (Liabilities:Taxes:IVA*)', value: '28618.00' },
        { label: 'Reserva fiscal total', formula: 'ISR + IVA', value: '48320.00' },
      ]),
    },
  };
}

/* ---------------------------------------------------------------- invoicing */

export const INVOICE_REGISTER: InvoiceRegister = {
  workspace: BIZ_WS_ID,
  as_of: '2026-09-06',
  currency: MXN,
  period: { start: null, end: null },
  counts: { issued: 8, open: 3 },
  issued: amt('757480.00'),
  collected: amt('504600.00'),
  outstanding: amt('252880.00'),
  aging: [
    { bucket: '0-30', amount: amt('0.00'), invoices: 0 },
    { bucket: '31-60', amount: amt('0.00'), invoices: 0 },
    { bucket: '61-90', amount: amt('111360.00'), invoices: 1 },
    { bucket: '90+', amount: amt('141520.00'), invoices: 2 },
  ],
  open_invoices: [
    {
      uuid: 'DEMO-BIZ-0000-0000-0008',
      fecha: '2026-03-09',
      client_rfc: '********2BB2',
      metodo_pago: 'PPD',
      total: amt('67280.00'),
      outstanding: amt('67280.00'),
      age_days: 181,
      bucket: '90+',
      reps: 0,
    },
    {
      uuid: 'DEMO-BIZ-0000-0000-0005',
      fecha: '2026-05-26',
      client_rfc: '********2BB2',
      metodo_pago: 'PPD',
      total: amt('74240.00'),
      outstanding: amt('74240.00'),
      age_days: 103,
      bucket: '90+',
      reps: 0,
    },
    {
      uuid: 'DEMO-BIZ-0000-0000-0007',
      fecha: '2026-06-12',
      client_rfc: '********1AA1',
      metodo_pago: 'PPD',
      total: amt('111360.00'),
      outstanding: amt('111360.00'),
      age_days: 86,
      bucket: '61-90',
      reps: 0,
    },
  ],
  top_clients: [
    {
      client_rfc: '********1AA1',
      invoices: 3,
      issued: amt('424560.00'),
      paid: amt('313200.00'),
      outstanding: amt('111360.00'),
    },
    {
      client_rfc: '********2BB2',
      invoices: 3,
      issued: amt('240120.00'),
      paid: amt('98600.00'),
      outstanding: amt('141520.00'),
    },
    {
      client_rfc: '********3CC3',
      invoices: 2,
      issued: amt('92800.00'),
      paid: amt('92800.00'),
      outstanding: amt('0.00'),
    },
  ],
  dso_days: '61',
  explain: explain(
    'Facturación: 757480.00 MXN emitidos, 504600.00 cobrados, 252880.00 por cobrar al 2026-09-06. DSO 61 días.',
    [
      { label: 'CFDI emitidos tipo I', value: '8' },
      { label: 'Total emitido', value: '757480.00' },
      {
        label: 'Cobrado',
        formula: 'PUE en su fecha de emisión; PPD sólo con REP (imp_pagado)',
        value: '504600.00',
      },
      { label: 'Por cobrar', formula: '757480.00 − 504600.00', value: '252880.00' },
      { label: 'DSO', formula: '(por cobrar ÷ emitido) × 180 días', value: '61' },
    ],
  ),
};

/* ------------------------------------------------------------------ payroll */

export const EMPLOYEES: Employee[] = [
  {
    id: 'emp-2865de47f7',
    name: 'E. T***',
    rfc: null,
    daily_salary: amt('315.04'),
    sbc_daily: amt('336.00'),
    state: 'NL',
    active: true,
    hired_on: '2025-03-01',
  },
  {
    id: 'emp-9f10c3ab54',
    name: 'B. M***',
    rfc: '******12AB3',
    daily_salary: amt('620.00'),
    sbc_daily: amt('661.00'),
    state: 'NL',
    active: true,
    hired_on: '2024-11-15',
  },
  {
    id: 'emp-4b77ee9012',
    name: 'C. R***',
    rfc: '******34CD5',
    daily_salary: amt('810.00'),
    sbc_daily: amt('864.00'),
    state: 'NL',
    active: true,
    hired_on: '2023-06-01',
  },
];

export const PAYROLL_RUNS: PayrollRunSummary[] = [
  {
    id: 'pay-2026-08-bc9a6751',
    period: '2026-08',
    days: '31',
    currency: MXN,
    gross: '54096.24',
    net: '46563.01',
    isr_retenido: '5996.18',
    imss_employee: '1537.05',
    imss_employer: '10723.44',
    infonavit: '2737.30',
    isn: '1622.89',
    employer_cost: '69179.87',
    txn_id: 'txn-a2a81c14f95a',
    created_at: '2026-09-06T23:30:45+00:00',
  },
  {
    id: 'pay-2026-07-19bd3c02',
    period: '2026-07',
    days: '31',
    currency: MXN,
    gross: '54096.24',
    net: '46563.01',
    isr_retenido: '5996.18',
    imss_employee: '1537.05',
    imss_employer: '10723.44',
    infonavit: '2737.30',
    isn: '1622.89',
    employer_cost: '69179.87',
    txn_id: 'txn-c81e4f0a2b71',
    created_at: '2026-08-05T18:12:03+00:00',
  },
];

const ISR_CITATION = {
  law: 'LISR',
  article: '96 (Anexo 8 RMF 2026, tabla A.V)',
  url: 'https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/anexos/Anexo-8-RMF-2026_DOF-28122025.pdf',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary' as const,
  excerpt:
    'Tarifa aplicable durante 2026 para el cálculo de los pagos provisionales mensuales a que se refieren los artículos 96 de la Ley del ISR y 175 de su Reglamento (DOF 28/12/2025).',
};

const INFONAVIT_CITATION = {
  law: 'LINFONAVIT',
  article: '29 fr. II',
  url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LIFNVT.pdf',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary' as const,
  excerpt:
    'Determinar el monto de las aportaciones del cinco por ciento sobre el salario de los trabajadores a su servicio.',
};

/** Line values are fixed strings; the totals below were summed with exact decimals. */
const LINE_INPUTS: {
  employee_id: string;
  name: string;
  rfc: string | null;
  gross: string;
  isr: string;
  isr_tarifa: string;
  subsidy: string;
  imss_employee: string;
  imss_employer: string;
  infonavit: string;
  net: string;
  capped: boolean;
}[] = [
  {
    employee_id: 'emp-2865de47f7',
    name: 'E. T***',
    rfc: null,
    gross: '9766.24',
    isr: '167.36',
    isr_tarifa: '703.58',
    subsidy: '536.22',
    imss_employee: '247.38',
    imss_employer: '2098.66',
    infonavit: '520.80',
    net: '9351.50',
    capped: false,
  },
  {
    employee_id: 'emp-9f10c3ab54',
    name: 'B. M***',
    rfc: '******12AB3',
    gross: '19220.00',
    isr: '2064.19',
    isr_tarifa: '2064.19',
    subsidy: '0.00',
    imss_employee: '559.14',
    imss_employer: '3762.20',
    infonavit: '961.00',
    net: '16596.67',
    capped: false,
  },
  {
    employee_id: 'emp-4b77ee9012',
    name: 'C. R***',
    rfc: '******34CD5',
    gross: '25110.00',
    isr: '3764.63',
    isr_tarifa: '3764.63',
    subsidy: '0.00',
    imss_employee: '730.53',
    imss_employer: '4862.58',
    infonavit: '1255.50',
    net: '20614.84',
    capped: true,
  },
];

function payrollLine(x: (typeof LINE_INPUTS)[number], days: string): PayrollLine {
  return {
    employee_id: x.employee_id,
    name: x.name,
    rfc: x.rfc,
    state: 'NL',
    days,
    gross: amt(x.gross),
    isr_retenido: amt(x.isr),
    isr_tarifa: amt(x.isr_tarifa),
    subsidio_empleo: amt(x.subsidy),
    imss_employee: amt(x.imss_employee),
    imss_employee_detail: {
      em_especie_excedente: '0.00',
      em_dinero: '26.04',
      gastos_medicos_pensionados: '39.06',
      invalidez_vida: '65.10',
      cesantia_vejez: '117.18',
    },
    imss_employer: amt(x.imss_employer),
    imss_employer_branches: [
      {
        branch: 'riesgos_trabajo',
        amount: amt('52.08'),
        formula: '0.5% × 10416.00 · prima mínima de riesgo (0.5%) (verify)',
      },
      {
        branch: 'em_especie_cuota_fija',
        amount: amt('741.87'),
        formula: '20.4% × 3636.61 · sobre la UMA, no sobre el SBC',
      },
      {
        branch: 'em_especie_excedente',
        amount: amt('0.00'),
        formula: '1.1% × 0.00 · sobre (SBC − 3 UMA)',
      },
      { branch: 'invalidez_vida', amount: amt('182.28'), formula: '1.75% × 10416.00' },
      {
        branch: 'cesantia_vejez',
        amount: amt('447.89'),
        formula: 'tabla 2026 por rango de SBC (verify)',
      },
      { branch: 'guarderias', amount: amt('104.16'), formula: '1% × 10416.00' },
    ],
    sbc_capped: x.capped,
    infonavit: amt(x.infonavit),
    net: amt(x.net),
    explain: {
      summary: `${x.name}: neto ${x.net} MXN = bruto ${x.gross} − ISR ${x.isr} − IMSS obrero ${x.imss_employee}.`,
      steps: [
        { label: 'Días del periodo', formula: null, value: days },
        { label: 'Percepción bruta', formula: null, value: x.gross },
        { label: 'ISR tarifa art. 96', formula: null, value: x.isr_tarifa },
        { label: 'Subsidio para el empleo', formula: null, value: x.subsidy },
        { label: 'ISR retenido', formula: null, value: x.isr },
        {
          label: 'Cuotas obreras IMSS',
          formula: 'LSS arts. 25, 106 II, 107, 147, 168 II b)',
          value: x.imss_employee,
        },
        { label: 'Cuotas patronales IMSS', formula: null, value: x.imss_employer },
        {
          label: 'Aportación INFONAVIT',
          formula: '5% (LINFONAVIT art. 29 fr. II)',
          value: x.infonavit,
        },
        { label: 'Neto a pagar', formula: null, value: x.net },
      ],
      citations: [ISR_CITATION, INFONAVIT_CITATION],
      rule_versions: [
        'mx.general.isr_provisional@2026.1',
        'mx.imss.employer_quotas@2026.1',
        'mx.infonavit.employer@2026.1',
      ],
      confidence: null,
    },
  };
}

export function payrollRun(id: string, period: string, days: string): PayrollRun {
  return {
    id,
    workspace: BIZ_WS_ID,
    period,
    days,
    currency: MXN,
    employees: LINE_INPUTS.length,
    lines: LINE_INPUTS.map((x) => payrollLine(x, days)),
    totals: {
      gross: amt('54096.24'),
      net: amt('46563.01'),
      isr_retenido: amt('5996.18'),
      imss_employee: amt('1537.05'),
      imss_employer: amt('10723.44'),
      infonavit: amt('2737.30'),
      isn: amt('1622.89'),
      employer_cost: amt('69179.87'),
    },
    isn: {
      value: amt('1622.89'),
      explain: {
        summary: 'ISN Nuevo León 3% sobre la nómina del periodo (verify).',
        steps: [
          { label: 'Base gravable', formula: null, value: '54096.24' },
          { label: 'Tasa ISN NL', formula: '3% (verify)', value: '0.03' },
          { label: 'ISN del periodo', formula: '54096.24 × 3%', value: '1622.89' },
        ],
        citations: [],
        rule_versions: ['mx.nl.isn@2026.1'],
        confidence: null,
      },
    },
    txn_id: `txn-${id.slice(-8)}`,
    status: 'draft',
    warnings: [
      'La tasa del ISN de Nuevo León (3%) no fue leída en la Ley de Hacienda del Estado (verify).',
      'La prima de riesgo de trabajo usa el mínimo de ley (0.5%) (verify).',
    ],
    explain: {
      summary: `Nómina ${period} (${days} días, ${LINE_INPUTS.length} empleados): costo patronal 69179.87 MXN.`,
      steps: [
        { label: 'Percepciones brutas', formula: null, value: '54096.24' },
        { label: 'ISR retenido', formula: null, value: '5996.18' },
        { label: 'Cuotas obreras IMSS', formula: null, value: '1537.05' },
        { label: 'Neto a pagar', formula: null, value: '46563.01' },
        { label: 'Cuotas patronales IMSS', formula: null, value: '10723.44' },
        { label: 'INFONAVIT', formula: null, value: '2737.30' },
        { label: 'ISN NL', formula: '3% de la nómina (verify)', value: '1622.89' },
        {
          label: 'Costo patronal',
          formula: 'bruto + IMSS patronal + INFONAVIT + ISN',
          value: '69179.87',
        },
      ],
      citations: [ISR_CITATION, INFONAVIT_CITATION],
      rule_versions: [
        'mx.general.isr_provisional@2026.1',
        'mx.imss.employer_quotas@2026.1',
        'mx.infonavit.employer@2026.1',
        'mx.nl.isn@2026.1',
      ],
      confidence: null,
    },
  };
}

/* ---------------------------------------------------------------- constants */

export const BIZ_CONSTANTS: BizConstants = {
  year: 2026,
  verified_on: '2026-09-06',
  constants: [
    {
      key: 'uma.daily',
      value: '117.31',
      citation: {
        law: 'INEGI',
        article: 'Comunicado de prensa 1/26 — UMA 2026',
        url: 'https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf',
        effective_from: '2026-02-01',
        effective_to: null,
        trust_tier: 'official_guidance',
        excerpt:
          'Los valores de la UMA que entrarán en vigor a partir del 1 de febrero de 2026 son: Diario 117.31 pesos mexicanos.',
      },
      source_url: 'https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf',
      verified: true,
      verified_on: '2026-09-06',
      note: 'Mensual 3,566.22 · anual 42,794.64. En vigor 2026-02-01 … 2027-01-31.',
    },
    {
      key: 'uma.monthly',
      value: '3566.22',
      citation: {
        law: 'INEGI',
        article: 'Comunicado de prensa 1/26 — UMA 2026',
        url: 'https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf',
        effective_from: '2026-02-01',
        effective_to: null,
        trust_tier: 'official_guidance',
        excerpt: "Mensual 3 566.22 pesos mexicanos.",
      },
      source_url: 'https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/uma/uma2026.pdf',
      verified: true,
      verified_on: '2026-09-06',
      note: null,
    },
    {
      key: 'salario_minimo.general_daily',
      value: '315.04',
      citation: {
        law: 'CONASAMI',
        article: 'Salarios mínimos 2026 (DOF 09-12-2025)',
        url: 'https://www.gob.mx/conasami/articulos/incremento-a-los-salarios-minimos-para-2026',
        effective_from: '2026-01-01',
        effective_to: null,
        trust_tier: 'official_guidance',
        excerpt:
          'A partir del 1 de enero del 2026 el salario mínimo general se incrementa de 278.80 a 315.04 pesos diarios.',
      },
      source_url: 'https://www.gob.mx/conasami/articulos/incremento-a-los-salarios-minimos-para-2026',
      verified: true,
      verified_on: '2026-09-06',
      note: 'Zona Libre de la Frontera Norte: 440.87.',
    },
    {
      key: 'infonavit.employer_rate',
      value: '0.05',
      citation: INFONAVIT_CITATION,
      source_url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LIFNVT.pdf',
      verified: true,
      verified_on: '2026-09-06',
      note: '5% sobre el SBC, topado igual que el IMSS.',
    },
    {
      key: 'imss.riesgos_trabajo.min_rate',
      value: '0.005',
      citation: {
        law: 'LSS',
        article: '73',
        url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LSS.pdf',
        effective_from: '2026-01-01',
        effective_to: null,
        trust_tier: 'primary',
        excerpt: 'Prima mínima de riesgo de trabajo.',
      },
      source_url: null,
      verified: false,
      verified_on: null,
      note: 'La prima real depende de la siniestralidad de la empresa (verify).',
    },
    {
      key: 'nl.isn.rate',
      value: '0.03',
      citation: {
        law: 'Ley de Hacienda del Estado de Nuevo León',
        article: 'ISN',
        url: null,
        effective_from: '2026-01-01',
        effective_to: null,
        trust_tier: 'professional',
        excerpt: null,
      },
      source_url: null,
      verified: false,
      verified_on: null,
      note: 'La tasa del 3% no fue leída en el texto oficial (verify).',
    },
    {
      key: 'isr.subsidio_empleo.monthly',
      value: '536.22',
      citation: {
        law: 'Decreto subsidio para el empleo',
        article: 'Anexo',
        url: null,
        effective_from: '2026-01-01',
        effective_to: null,
        trust_tier: 'professional',
        excerpt: null,
      },
      source_url: null,
      verified: false,
      verified_on: null,
      note: 'Falta confirmarlo contra el decreto 2026 (verificar).',
    },
  ],
  unverified: [
    'imss.cesantia_vejez.employer_table_2026',
    'isr.subsidio_empleo.monthly',
    'isr.subsidio_empleo.income_cap_monthly',
    'nl.isn.rate',
    'imss.riesgos_trabajo.min_rate',
  ],
};

/* ----------------------------------------------------------------- insights */

const SAT_CITATION = {
  law: 'RMF 2026',
  article: 'declaración prellenada RESICO',
  url: 'https://www.sat.gob.mx/',
  effective_from: null,
  effective_to: null,
  trust_tier: 'official_guidance' as const,
  excerpt:
    'La declaración mensual de RESICO se prellena con los CFDI de ingreso, egreso y los complementos de pago; el prellenado supone cobrada toda factura PUE.',
};

export function insightsFor(ws: string, period: string): Insight[] {
  const due = `${period.slice(0, 4)}-${String(Number(period.slice(5, 7)) + 1).padStart(2, '0')}-17`;
  return [
    {
      id: 'ins-pue_not_collected-109c38a31789734d',
      ws_id: ws,
      kind: 'pue_not_collected',
      severity: 'warn',
      title: 'Factura PUE sin cobrar',
      body: '1 factura(s) PUE que el SAT da por cobradas nunca llegaron al banco (13920.00 MXN). El ISR se paga igual; emite PPD la próxima vez.',
      amount: amt('13920.00'),
      due_date: due,
      explain: {
        summary:
          '1 factura(s) PUE que el SAT da por cobradas nunca llegaron al banco (13920.00 MXN).',
        steps: [
          { label: 'PUE sin depósito AGO-PUE-E', formula: null, value: '13920.00' },
          { label: 'Total', formula: null, value: '13920.00' },
        ],
        citations: [SAT_CITATION],
        rule_versions: [],
        confidence: null,
      },
      actions: [{ label: 'Ver cierre del mes', href: `/api/tax/mx/resico/${ws}/${period}` }],
    },
    {
      id: 'ins-deposit_without_cfdi-7489b150530b4e5d',
      ws_id: ws,
      kind: 'deposit_without_cfdi',
      severity: 'warn',
      title: 'Depósito sin CFDI',
      body: '1 depósito(s) sin CFDI que los respalde (6500.00 MXN). En RESICO todo ingreso debe facturarse.',
      amount: amt('6500.00'),
      due_date: due,
      explain: {
        summary: '1 depósito(s) sin CFDI que los respalde (6500.00 MXN).',
        steps: [
          { label: '2026-08-15 Deposito En Efectivo Ventanilla', formula: null, value: '6500.00' },
          { label: 'Total', formula: null, value: '6500.00' },
        ],
        citations: [SAT_CITATION],
        rule_versions: [],
        confidence: null,
      },
      actions: [{ label: 'Ver conciliación', href: `/api/ingest/${ws}/reconcile?period=${period}` }],
    },
    {
      id: 'ins-you_may_owe-76f78851be2d1b36',
      ws_id: ws,
      kind: 'you_may_owe',
      severity: 'urgent',
      title: 'Podrías deber ~5527.00 MXN',
      body: `Con lo declarado hasta ahora podrías deber aproximadamente 5527.00 MXN el ${due}.`,
      amount: amt('5527.00'),
      due_date: due,
      explain: {
        summary: `Con lo declarado hasta ahora podrías deber aproximadamente 5527.00 MXN el ${due}.`,
        steps: [
          { label: 'ISR', formula: null, value: '407.00' },
          { label: 'IVA a pagar', formula: null, value: '5120.00' },
          { label: 'Total estimado', formula: 'ISR + IVA', value: '5527.00' },
        ],
        citations: [SAT_CITATION],
        rule_versions: ['mx.resico.isr_monthly@2026.1'],
        confidence: null,
      },
      actions: [{ label: 'Ver cierre del mes', href: `/api/tax/mx/resico/${ws}/${period}` }],
    },
    {
      id: 'ins-goal_off_track-2b0c1d43aa77',
      ws_id: ws,
      kind: 'goal_off_track',
      severity: 'info',
      title: "Meta 'Fondo de emergencia' fuera de ritmo",
      body: 'El ritmo de ahorro reciente no alcanza lo que requiere la meta para 2027-06-30.',
      amount: null,
      due_date: '2027-06-30',
      explain: {
        summary: 'Aportación mensual requerida 4166.67 MXN; ritmo reciente 2900.00 MXN.',
        steps: [
          { label: 'Requerido / mes', formula: null, value: '4166.67' },
          { label: 'Ritmo reciente', formula: null, value: '2900.00' },
        ],
        citations: [],
        rule_versions: [],
        confidence: null,
      },
      actions: [{ label: 'Ver metas', href: `/api/pf/${ws}/goals` }],
    },
  ];
}

export function calendarFor(ws: string, from: string, to: string): CalendarEntry[] {
  const year = Number(from.slice(0, 4));
  const out: CalendarEntry[] = [];
  for (let m = 1; m <= 12; m += 1) {
    const mm = String(m).padStart(2, '0');
    out.push({
      kind: 'mx_monthly_declaration',
      date: `${year}-${mm}-17`,
      period: `${year}-${String(m - 1 || 12).padStart(2, '0')}`,
      title: 'Declaración mensual RESICO / DIOT',
      note: '(verify) whether DIOT is filed separately from the monthly declaration',
    });
    out.push({ kind: 'card_due', date: `${year}-${mm}-10`, title: 'BBVA Azul due' });
  }
  out.push({ kind: 'goal_target_date', date: `${year + 1}-06-30`, title: 'Fondo de emergencia' });
  return out
    .filter((e) => e.date >= from && e.date <= to)
    .sort((a, b) => (a.date < b.date ? -1 : 1));
}

export function digestFor(ws: string, period: string, insights: Insight[]): string {
  const urgent = insights.filter((i) => i.severity === 'urgent').length;
  const warn = insights.filter((i) => i.severity === 'warn').length;
  const info = insights.filter((i) => i.severity === 'info').length;
  const lines = insights.map(
    (i) => `${i.severity === 'urgent' ? '!!' : i.severity === 'warn' ? '!' : '·'} ${i.title}: ${i.body}`,
  );
  return [
    `Resumen de Aurum (${ws}, ${period})`,
    `${urgent} urgente(s), ${warn} de atención, ${info} informativo(s).`,
    '',
    ...lines,
  ].join('\n');
}

/* ------------------------------------------------------------------ reports */

const PACK_META: { pack: string; es: string; en: string; period_kind: ReportPack['period_kind'] }[] = [
  { pack: 'monthly-review', es: 'Revisión mensual', en: 'Monthly review', period_kind: 'month' },
  { pack: 'net-worth', es: 'Patrimonio neto', en: 'Net worth', period_kind: 'none' },
  { pack: 'mx-annual', es: 'Anual MX (RESICO)', en: 'MX annual (RESICO)', period_kind: 'year' },
  { pack: 'us-organizer', es: 'Organizador US', en: 'US organizer', period_kind: 'year' },
  { pack: 'client-pack', es: 'Paquete para el cliente', en: 'Client pack', period_kind: 'month' },
];

export function reportCatalog(ws: string, kind: string, jurisdictions: string[]) {
  return {
    workspace: ws,
    kind,
    jurisdictions,
    packs: PACK_META.map((p) => ({
      pack: p.pack,
      title: { es: p.es, en: p.en },
      applicable:
        p.pack === 'mx-annual'
          ? jurisdictions.includes('MX')
          : p.pack === 'us-organizer'
            ? jurisdictions.includes('US')
            : p.pack === 'client-pack'
              ? kind === 'advisory' || kind === 'business'
              : true,
      period_kind: p.period_kind,
      url: `/api/reports/${ws}/${p.pack}`,
    })),
  };
}

export function reportPreview(ws: string, pack: string, period: string | null, lang: 'es' | 'en'): ReportPreview {
  const meta = PACK_META.find((p) => p.pack === pack);
  return {
    title: `${meta ? meta[lang] : pack}${period ? ` — ${period}` : ''}`,
    workspace: ws,
    period,
    lang,
    draft: pack === 'mx-annual' || pack === 'us-organizer',
    watermark_text: pack === 'mx-annual' || pack === 'us-organizer' ? 'BORRADOR / DRAFT' : null,
    generated_at: '2026-09-06T23:32:21+00:00',
    rule_versions: pack === 'mx-annual' ? ['mx.resico.isr_monthly@2026.1'] : [],
    sections: [
      {
        title: 'Ingreso vs. gasto / Income vs. spend',
        kpis: [
          { label: 'Ingreso / Income', value: '51500.00 MXN', note: null },
          { label: 'Gasto / Expense', value: '6160.00 MXN', note: null },
          { label: 'Neto / Net', value: '45340.00 MXN', note: null },
          { label: 'Tasa de ahorro / Savings rate', value: '88.0%', note: null },
        ],
        tables: [],
        notes: [],
        explains: [
          {
            summary:
              'La revisión mensual agrega los movimientos del período; deltas vs. el mes anterior.',
            steps: [],
            citations: [],
          },
        ],
      },
      {
        title: 'Principales categorías / Top labels',
        kpis: [],
        tables: [
          {
            title: '',
            columns: ['Label', 'Amount'],
            rows: [
              ['Expenses:Software', '5000.00'],
              ['Expenses:Food:Restaurants', '1160.00'],
            ],
          },
        ],
        notes: [],
        explains: [],
      },
      {
        title: 'Presupuestos / Budgets',
        kpis: [],
        tables: [
          {
            title: '',
            columns: ['Label', 'Budget', 'Spent', 'Left'],
            rows: [
              ['Comida fuera', '3500 MXN', '1160 MXN', '2340 MXN'],
              ['Súper', '6000 MXN', '0 MXN', '6000 MXN'],
            ],
          },
        ],
        notes: ['Los presupuestos sin gasto registrado se muestran igual.'],
        explains: [],
      },
    ],
    warnings: pack === 'mx-annual' ? ['Documento en borrador: Aurum no presenta declaraciones.'] : [],
  };
}

export function reportHtml(preview: ReportPreview): string {
  const sections = preview.sections
    .map(
      (s) =>
        `<section><h2>${s.title}</h2>` +
        (s.kpis.length
          ? `<ul>${s.kpis.map((k) => `<li><b>${k.label}</b>: ${k.value}</li>`).join('')}</ul>`
          : '') +
        s.tables
          .map(
            (tb) =>
              `<table border="1" cellpadding="4" cellspacing="0"><thead><tr>${tb.columns
                .map((c) => `<th>${c}</th>`)
                .join('')}</tr></thead><tbody>${tb.rows
                .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`)
                .join('')}</tbody></table>`,
          )
          .join('') +
        '</section>',
    )
    .join('');
  return `<!doctype html><html lang="${preview.lang}"><head><meta charset="utf-8"><title>${preview.title}</title><style>body{font-family:Georgia,serif;margin:28px;color:#1c1a17}h1{font-size:20px}h2{font-size:15px;margin-top:22px}table{border-collapse:collapse;font-size:13px}</style></head><body><h1>${preview.title}</h1>${
    preview.watermark_text ? `<p style="color:#a03028"><b>${preview.watermark_text}</b></p>` : ''
  }${sections}</body></html>`;
}

export const ARCHIVE_SEED: ArchivedReport[] = [];

/* ---------------------------------------------------------------- workflows */

export const WORKFLOW_CATALOG: WorkflowCatalog = {
  endpoints: [
    { method: 'GET', path: '/tax/mx/resico/{ws}/{period}', summary: 'Cierre del mes MX' },
    { method: 'GET', path: '/ingest/{ws}/reconcile', summary: 'Tablero de conciliación' },
    { method: 'GET', path: '/insights/{ws}', summary: 'Avisos del periodo' },
    { method: 'GET', path: '/insights/{ws}/digest', summary: 'Resumen para Telegram' },
    { method: 'GET', path: '/reports/{ws}/{pack}', summary: 'Renderizar un paquete' },
    { method: 'POST', path: '/reports/{ws}/{pack}/archive', summary: 'Archivar un paquete' },
    { method: 'GET', path: '/reports/{ws}/{pack}/archive', summary: 'Historial de archivos' },
    { method: 'GET', path: '/business/{ws}/kpis', summary: 'KPIs del negocio' },
    { method: 'POST', path: '/business/{ws}/payroll/run', summary: 'Correr la nómina (borrador)' },
    { method: 'GET', path: '/pf/{ws}/budgets/status', summary: 'Estado de presupuestos' },
    { method: 'GET', path: '/audit', summary: 'Audit Log' },
  ],
};

/** Each seed's `yaml` is the source of truth; `definition` is what the server would parse
    out of it — the mock keeps both in sync by construction instead of parsing the yaml. */
const monthCloseDefinition: WorkflowDefinition = {
  id: 'law-watch',
  name: 'cierre-mensual',
  description: 'Cierre del mes: conciliar, revisar avisos y archivar la revisión mensual.',
  schedule: '0 9 17 * *',
  steps: [
    { id: 'reconcile', method: 'GET', path: '/ingest/{{ ws }}/reconcile?period={{ period }}' },
    { id: 'tax_close', method: 'GET', path: '/tax/mx/resico/{{ ws }}/{{ period }}' },
    {
      id: 'archive_review',
      method: 'POST',
      path: '/reports/{{ ws }}/monthly-review/archive?period={{ period }}',
    },
  ],
};

const weeklyDigestDefinition: WorkflowDefinition = {
  id: 'weekly-digest',
  name: 'resumen-semanal',
  description: 'Resumen de avisos cada lunes.',
  schedule: '0 8 * * 1',
  steps: [
    { id: 'insights', method: 'GET', path: '/insights/{{ ws }}' },
    { id: 'digest', method: 'GET', path: '/insights/{{ ws }}/digest' },
  ],
};

const definitionToYaml = (d: WorkflowDefinition) =>
  `id: ${d.id}
name: ${d.name}
description: ${d.description ?? ''}
schedule: ${d.schedule ?? 'null'}
steps:
${d.steps
  .map((s) => `  - id: ${s.id}\n    method: ${s.method}\n    path: ${s.path}`)
  .join('\n')}
`;

export interface WorkflowSeed {
  id: string;
  workspace: string;
  name: string;
  schedule: string | null;
  created_at: string;
  updated_at: string | null;
  yaml: string;
  definition: WorkflowDefinition;
}

export const WORKFLOWS_SEED: WorkflowSeed[] = [
  {
    id: 'law-watch',
    workspace: '',
    name: 'cierre-mensual',
    schedule: '0 9 17 * *',
    created_at: '2026-09-06T12:00:00+00:00',
    updated_at: null,
    yaml: definitionToYaml(monthCloseDefinition),
    definition: monthCloseDefinition,
  },
  {
    id: 'weekly-digest',
    workspace: '',
    name: 'resumen-semanal',
    schedule: '0 8 * * 1',
    created_at: '2026-09-06T12:00:00+00:00',
    updated_at: null,
    yaml: definitionToYaml(weeklyDigestDefinition),
    definition: weeklyDigestDefinition,
  },
];

export const PROPOSED_YAML = `id: recordatorio-de-cobranza
name: recordatorio-de-cobranza
description: Revisar facturas vencidas y preparar recordatorios
schedule: null
steps:
  - id: invoices
    method: GET
    path: /business/{{ ws }}/invoices
  - id: insights
    method: GET
    path: /insights/{{ ws }}
`;
