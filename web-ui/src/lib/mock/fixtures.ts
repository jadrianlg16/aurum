/**
 * Fixtures for the in-browser fake API — reusing the REAL numbers captured live against the
 * `demo-mx` workspace in `web-ui/docs/api-samples.json` wherever a sample exists, so the mock
 * and the real API agree on the demo dataset. Endpoints not covered by api-samples.json
 * (research/ask, watch/*) keep synthetic but internally-consistent data.
 */
import type {
  AccountsOverview,
  Amount,
  Budget,
  Cards,
  CFDI,
  ChangesResponse,
  Citation,
  Explain,
  Goals,
  Health,
  IncomeOverview,
  InboxItem,
  Labels,
  Loans,
  MonthClose,
  MonthlyReview,
  RecurringOverview,
  ResearchAnswer,
  Rules,
  Transaction,
  VaultStatus,
  SyncJobs,
  Workspace,
} from '../types';

import { US_WORKSPACE } from './fixtures-tax';

export const WS_ID = 'demo-mx';
export const PERIODS = ['2026-06', '2026-07', '2026-08'] as const;
export const DEMO_PERIOD = '2026-08';

export const mx = (amount: string): Amount => ({ amount, currency: 'MXN' });

/* ---------------------------------------------------------------- citations */

export const CITE_113E: Citation = {
  law: 'LISR',
  article: '113-E',
  url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt:
    'Pago mensual: tasa aplicada a la totalidad de los ingresos amparados por CFDI efectivamente cobrados en el mes, sin IVA y sin deducción alguna.',
  // Research graph layer: what the article's text points at, for the chips on the card.
  related: [
    { law: 'LISR', article: '113-F' },
    { law: 'RMF', article: '3.13.10' },
    { law: 'CFF', article: '29-A' },
  ],
};

export const CITE_LIVA5: Citation = {
  law: 'LIVA',
  article: '5',
  url: 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LIVA.pdf',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'primary',
  excerpt:
    'Para que sea acreditable el IVA: que corresponda a bienes o servicios estrictamente indispensables, que conste por separado en el CFDI y que haya sido efectivamente pagado.',
  related: [
    { law: 'LIVA', article: '1-B' },
    { law: 'RMF', article: '2.7.1.32' },
  ],
};

export const CITE_RMF: Citation = {
  law: 'RMF 2026',
  article: 'prefill RESICO (CFDI de ingreso, egreso y complementos de pago)',
  url: 'https://www.sat.gob.mx/',
  effective_from: '2026-01-01',
  effective_to: null,
  trust_tier: 'official_guidance',
  excerpt:
    'La declaración de RESICO se prellena con los CFDI: PUE en el mes de emisión, REP en el mes de la FechaPago; PPD sin REP no se considera cobrado.',
};

const explain = (
  summary: string,
  steps: { label: string; formula?: string | null; value: string }[],
  citations: Citation[],
  rule_versions: string[],
  confidence: number | null = null,
): Explain => ({
  summary,
  steps: steps.map((s) => ({ label: s.label, formula: s.formula ?? null, value: s.value })),
  citations,
  rule_versions,
  confidence,
});

/* --------------------------------------------------------------- workspaces */

/**
 * The mock's default space is a personal, NON-demo one ("Mis finanzas") so the
 * resolver lands on it exactly as it would on a real install; the demos follow, flagged
 * `profile.demo: true`, and the list is ordered personal-first as the server orders it.
 */
export const PERSONAL_WS_ID = 'mock-personal';

export const PERSONAL_WORKSPACE: Workspace = {
  id: PERSONAL_WS_ID,
  name: 'Mis finanzas',
  kind: 'personal',
  jurisdictions: ['MX'],
  base_currency: 'MXN',
  language: 'es',
  profile: { country: 'MX', state: 'NL', demo: false },
  created_at: '2026-09-01T09:00:00.000000Z',
  ui_mode: 'simple',
  modules: {},
  protected: true,
  hidden: false,
};

export const WORKSPACES: Workspace[] = [
  PERSONAL_WORKSPACE,
  {
    id: WS_ID,
    name: 'Demo México (RESICO)',
    kind: 'personal',
    jurisdictions: ['MX'],
    base_currency: 'MXN',
    language: 'es',
    profile: { rfc: '*********1000', regime: 'RESICO_PF', state: 'NL', country: 'MX', demo: true },
    created_at: '2026-09-05T20:45:11.286491Z',
    protected: false,
    hidden: false,
  },
  // The second demo workspace: US/Texas sole proprietor, USD, English.
  US_WORKSPACE,
];

/** No `data_dir`; `auth`, `bind` and the migration `schema` map are what the UI reads. */
export const HEALTH: Health = {
  ok: true,
  version: '0.1.0-mock',
  llm: { provider: 'ollama', model: 'llama3.1:8b', cloud_opt_in: false },
  demo_mode: false,
  auth: { required: false, source: 'none' },
  bind: '127.0.0.1',
  schema: { pf: 4, organizer: 1 },
};

/* -------------------------------------------------------------------- CFDIs */

const concepto = (clave_prod_serv: string, descripcion: string, valor_unitario: string) => ({
  clave_prod_serv,
  descripcion,
  cantidad: '1',
  valor_unitario,
  importe: valor_unitario,
});

export const CFDIS: CFDI[] = [
  {
    uuid: 'AGO-PUE-D',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-05T10:00:00',
    emisor_rfc: 'XAXX010101000',
    emisor_nombre: 'Contribuyente Demo',
    receptor_rfc: 'DPM010101AA1',
    receptor_nombre: 'Cliente Alfa SA de CV',
    subtotal: '25000.00',
    total: '29000.00',
    moneda: 'MXN',
    metodo_pago: 'PUE',
    forma_pago: '03',
    uso_cfdi: 'G03',
    impuestos_trasladados: '4000.00',
    impuestos_retenidos: '312.50',
    isr_retenido: '312.50',
    iva_retenido: '0',
    iva_trasladado: '4000.00',
    conceptos: [concepto('84111506', 'Servicios profesionales', '25000.00')],
    pagos: [],
    direction: 'emitido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/AGO-PUE-D.xml',
  },
  {
    uuid: 'REC-AGO-1',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-07T12:00:00',
    emisor_rfc: 'DPR010101CC3',
    emisor_nombre: 'Proveedor Gamma SA de CV',
    receptor_rfc: 'XAXX010101000',
    receptor_nombre: 'Contribuyente Demo',
    subtotal: '5000.00',
    total: '5800.00',
    moneda: 'MXN',
    metodo_pago: 'PUE',
    forma_pago: '03',
    uso_cfdi: 'G03',
    impuestos_trasladados: '800.00',
    impuestos_retenidos: '0',
    isr_retenido: '0',
    iva_retenido: '0',
    iva_trasladado: '800.00',
    conceptos: [concepto('84111506', 'Licencias de software', '5000.00')],
    pagos: [],
    direction: 'recibido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/REC-AGO-1.xml',
  },
  {
    uuid: 'REC-AGO-2',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-09T14:00:00',
    emisor_rfc: 'DPR010101CC3',
    emisor_nombre: 'Proveedor Gamma SA de CV',
    receptor_rfc: 'XAXX010101000',
    receptor_nombre: 'Contribuyente Demo',
    subtotal: '1000.00',
    total: '1160.00',
    moneda: 'MXN',
    metodo_pago: 'PUE',
    forma_pago: '01',
    uso_cfdi: 'G03',
    impuestos_trasladados: '160.00',
    impuestos_retenidos: '0',
    isr_retenido: '0',
    iva_retenido: '0',
    iva_trasladado: '160.00',
    conceptos: [concepto('84111506', 'Comida de trabajo', '1000.00')],
    pagos: [],
    direction: 'recibido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/REC-AGO-2.xml',
  },
  {
    uuid: 'AGO-PUE-E',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-18T18:05:00',
    emisor_rfc: 'XAXX010101000',
    emisor_nombre: 'Contribuyente Demo',
    receptor_rfc: 'DPM010101AA1',
    receptor_nombre: 'Cliente Alfa SA de CV',
    subtotal: '12000.00',
    total: '13920.00',
    moneda: 'MXN',
    metodo_pago: 'PUE',
    forma_pago: '03',
    uso_cfdi: 'G03',
    impuestos_trasladados: '1920.00',
    impuestos_retenidos: '0',
    isr_retenido: '0',
    iva_retenido: '0',
    iva_trasladado: '1920.00',
    conceptos: [concepto('84111506', 'Soporte mensual — agosto', '12000.00')],
    pagos: [],
    direction: 'emitido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/AGO-PUE-E.xml',
  },
  {
    uuid: 'AGO-PPD-F',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-11T09:00:00',
    emisor_rfc: 'XAXX010101000',
    emisor_nombre: 'Contribuyente Demo',
    receptor_rfc: 'DPM010101AA1',
    receptor_nombre: 'Cliente Alfa SA de CV',
    subtotal: '8000.00',
    total: '9280.00',
    moneda: 'MXN',
    metodo_pago: 'PPD',
    forma_pago: '99',
    uso_cfdi: 'G03',
    impuestos_trasladados: '1280.00',
    impuestos_retenidos: '0',
    isr_retenido: '0',
    iva_retenido: '0',
    iva_trasladado: '1280.00',
    conceptos: [concepto('84111506', 'Proyecto de integración', '8000.00')],
    pagos: [],
    direction: 'emitido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/AGO-PPD-F.xml',
  },
  {
    uuid: 'REC-AGO-3',
    version: '4.0',
    tipo: 'I',
    fecha: '2026-08-15T17:10:00',
    emisor_rfc: 'TEC900101AB1',
    emisor_nombre: 'TecnoStore SA de CV',
    receptor_rfc: 'XAXX010101000',
    receptor_nombre: 'Contribuyente Demo',
    subtotal: '20000.00',
    total: '23200.00',
    moneda: 'MXN',
    metodo_pago: 'PUE',
    forma_pago: '04',
    uso_cfdi: 'I04',
    impuestos_trasladados: '3200.00',
    impuestos_retenidos: '0',
    isr_retenido: '0',
    iva_retenido: '0',
    iva_trasladado: '3200.00',
    conceptos: [concepto('43211508', 'Equipo de cómputo', '20000.00')],
    pagos: [],
    direction: 'recibido',
    raw_path: 'workspaces/demo-mx/docs/cfdi/REC-AGO-3.xml',
  },
];

/* ---------------------------------------------------------------- month close */

const PREFILL_EXPLAIN_2026_08 = explain(
  'Prellenado esperado para 2026-08: ingreso 37000.00, ISR 407.00, IVA acreditable 800.00 MXN.',
  [
    { label: 'Ingreso que el SAT dará por cobrado', formula: null, value: '37000.00' },
    { label: 'ISR que mostrará el prellenado', formula: null, value: '407.00' },
    {
      label: 'IVA acreditable del prellenado',
      formula: 'sólo gastos generales pagados por medios bancarios',
      value: '800.00',
    },
  ],
  [CITE_RMF],
  ['mx.resico.isr_monthly@2026.1', 'mx.resico.income_cash_basis@2026.1'],
);

export const MONTH_CLOSE: Record<string, MonthClose> = {
  '2026-08': {
    period: '2026-08',
    workspace: WS_ID,
    currency: 'MXN',
    income: {
      collected: mx('37000.00'),
      by_rule: [{ rule: 'mx.resico.income_cash_basis@2026.1', value: mx('37000.00') }],
      explain: explain(
        'Ingreso efectivamente cobrado en 2026-08: 37000.00 MXN (2 documento(s), IVA excluido).',
        [
          { label: 'PUE emitido AGO-PUE-D', formula: '2026-08-05 · bruto 29000.00 → sin IVA 25000.00', value: '25000.00' },
          { label: 'PUE emitido AGO-PUE-E', formula: '2026-08-18 · bruto 13920.00 → sin IVA 12000.00', value: '12000.00' },
          { label: 'excluido AGO-PPD-F (ppd_missing_rep)', formula: null, value: '8000.00' },
        ],
        [CITE_RMF],
        ['mx.resico.income_cash_basis@2026.1'],
      ),
    },
    isr: {
      value: mx('407.00'),
      explain: explain(
        'ISR RESICO del mes: 407.00 MXN = 37000.00 × 1.1% (sin deducciones).',
        [
          { label: 'Ingreso cobrado del mes (sin IVA)', formula: null, value: '37000.00' },
          { label: 'Deducciones aplicables', formula: 'art. 113-E: ninguna', value: '0.00' },
          { label: 'Tramo de la tabla mensual', formula: 'LISR art. 113-E (2026)', value: '≤ 50000.00' },
        ],
        [CITE_113E],
        ['mx.resico.isr_monthly@2026.1'],
      ),
    },
    iva: {
      trasladado: mx('5920.00'),
      acreditable: mx('800.00'),
      payable: mx('5120.00'),
      explain: explain(
        'IVA de 2026-08: trasladado 5920.00 − acreditable 800.00 = 5120.00 MXN a cargo',
        [
          { label: 'IVA trasladado (sobre lo cobrado)', formula: 'Σ (bruto − neto) PUE/REP', value: '5920.00' },
          { label: 'IVA acreditable REC-AGO-1', formula: 'uso G03 · forma de pago 03', value: '800.00' },
          { label: 'no acreditable REC-AGO-2 (cash_paid_expense)', formula: null, value: '160.00' },
        ],
        [CITE_LIVA5],
        ['mx.iva.monthly@2026.1'],
      ),
    },
    retentions: { isr: mx('312.50'), iva: mx('0.00') },
    prefill_expected: {
      income: mx('37000.00'),
      isr: mx('407.00'),
      iva_acreditable: mx('800.00'),
      explain: PREFILL_EXPLAIN_2026_08,
    },
    diffs: [
      {
        kind: 'pue_not_collected',
        amount: mx('13920.00'),
        documents: ['AGO-PUE-E'],
        explain: explain(
          '1 factura(s) PUE que el SAT da por cobradas nunca llegaron al banco (13920.00 MXN). El ISR se paga igual; emite PPD la próxima vez.',
          [
            { label: 'PUE sin depósito AGO-PUE-E', formula: null, value: '13920.00' },
            { label: 'Total', formula: null, value: '13920.00' },
          ],
          [CITE_RMF],
          [],
        ),
      },
      {
        kind: 'ppd_missing_rep',
        amount: mx('9280.00'),
        documents: ['AGO-PPD-F'],
        explain: explain(
          '1 factura(s) PPD sin complemento de pago (9280.00 MXN): no se declaran hasta que exista el REP.',
          [
            { label: 'PPD sin REP AGO-PPD-F', formula: null, value: '9280.00' },
            { label: 'Total', formula: null, value: '9280.00' },
          ],
          [CITE_RMF],
          [],
        ),
      },
      {
        kind: 'deposit_without_cfdi',
        amount: mx('6500.00'),
        documents: [],
        explain: explain(
          '1 depósito(s) sin CFDI que los respalde (6500.00 MXN). En RESICO todo ingreso debe facturarse.',
          [
            { label: '2026-08-15 Deposito En Efectivo Ventanilla', formula: null, value: '6500.00' },
            { label: 'Total', formula: null, value: '6500.00' },
          ],
          [CITE_RMF],
          [],
        ),
      },
      {
        kind: 'cash_paid_expense',
        amount: mx('160.00'),
        documents: ['REC-AGO-2'],
        explain: explain(
          'El IVA de 160.00 MXN de comida de trabajo pagada en efectivo no es acreditable: LIVA art. 5 exige medio de pago bancarizado.',
          [
            { label: 'IVA trasladado en el CFDI', formula: null, value: '160.00' },
            { label: 'Forma de pago', formula: '01 — efectivo', value: '0.00' },
          ],
          [CITE_LIVA5],
          [],
        ),
      },
      {
        kind: 'fixed_asset_iva',
        amount: mx('3200.00'),
        documents: ['REC-AGO-3'],
        explain: explain(
          'Aurum acredita el IVA del equipo de cómputo; el prellenado del SAT excluye el IVA de activos fijos.',
          [
            { label: 'IVA del activo fijo', formula: null, value: '3200.00' },
            { label: 'Incluido por Aurum', formula: null, value: '0.00' },
            { label: 'Incluido por el prellenado', formula: null, value: '0.00' },
          ],
          [CITE_LIVA5, CITE_RMF],
          [],
        ),
      },
    ],
    deadline: '2026-09-17',
    status: 'draft',
    warnings: [
      'El prellenado del SAT y la realidad bancaria no coinciden: revisa las diferencias antes de declarar.',
      'Borrador. Aurum nunca transmite ni firma una declaración.',
    ],
  },
};

/* -------------------------------------------------------------------- rules */

export const RULES: Rules = [
  {
    id: 'mx.iva.monthly',
    version: '2026.1',
    rule_version: 'mx.iva.monthly@2026.1',
    jurisdiction: 'MX',
    effective_from: '2026-01-01',
    effective_to: null,
    citation: CITE_LIVA5,
    doc: 'IVA a cargo del mes = IVA trasladado cobrado − IVA acreditable (LIVA art. 5).',
  },
  {
    id: 'mx.resico.income_cash_basis',
    version: '2026.1',
    rule_version: 'mx.resico.income_cash_basis@2026.1',
    jurisdiction: 'MX',
    effective_from: '2026-01-01',
    effective_to: null,
    citation: CITE_RMF,
    doc: 'Collected RESICO income for a month under SAT’s prefill rules (PUE / REP / PPD).',
  },
  {
    id: 'mx.resico.isr_monthly',
    version: '2026.1',
    rule_version: 'mx.resico.isr_monthly@2026.1',
    jurisdiction: 'MX',
    effective_from: '2026-01-01',
    effective_to: null,
    citation: CITE_113E,
    doc: 'Monthly RESICO ISR: tiered flat rate on the month’s collected income, no deductions (art. 113-E).',
  },
];

/* -------------------------------------------------------------------- ledger */

const txn = (
  date: string,
  payee: string | null,
  narration: string,
  postings: { account: string; amount?: Amount | null }[],
  meta: Record<string, string> = {},
  links: string[] = [],
): Transaction => ({
  date,
  payee,
  narration,
  postings: postings.map((p) => ({ account: p.account, amount: p.amount ?? null })),
  tags: ['demo'],
  links,
  meta,
});

export const JOURNAL: Transaction[] = [
  txn(
    '2026-08-06',
    'Spei Recibido Cliente Alfa',
    'SPEI RECIBIDO CLIENTE ALFA',
    [
      { account: 'Assets:Bank:BBVA', amount: mx('28687.50') },
      { account: 'Assets:Taxes:ISR-Retenido', amount: mx('312.50') },
      { account: 'Income:Freelance', amount: mx('-25000.00') },
      { account: 'Liabilities:Taxes:IVA-Trasladado', amount: mx('-4000.00') },
    ],
    { cfdi_uuid: 'AGO-PUE-D', source: 'demo-bank' },
    ['bank-2026-08-06-AGO-PUE-D'],
  ),
  txn(
    '2026-08-07',
    'Pago Proveedor Gamma',
    'PAGO PROVEEDOR GAMMA',
    [
      { account: 'Expenses:Software', amount: mx('5000.00') },
      { account: 'Assets:Taxes:IVA-Acreditable', amount: mx('800.00') },
      { account: 'Assets:Bank:BBVA', amount: mx('-5800.00') },
    ],
    { cfdi_uuid: 'REC-AGO-1', source: 'demo-bank' },
    ['bank-2026-08-07-REC-AGO-1'],
  ),
  txn(
    '2026-08-09',
    'Proveedor Gamma SA de CV',
    'Comida de trabajo pagada en efectivo',
    [
      { account: 'Expenses:Food:Restaurants', amount: mx('1160.00') },
      { account: 'Assets:Cash', amount: mx('-1160.00') },
    ],
    { cfdi_uuid: 'REC-AGO-2', forma_pago: '01', source: 'demo' },
    ['cash-REC-AGO-2'],
  ),
  txn(
    '2026-08-11',
    'Cliente Alfa SA de CV',
    'Emisión CFDI PPD proyecto de integración',
    [
      { account: 'Assets:Receivable:Clients', amount: mx('9280.00') },
      { account: 'Income:Freelance', amount: mx('-8000.00') },
      { account: 'Liabilities:Taxes:IVA-Trasladado', amount: mx('-1280.00') },
    ],
    { cfdi_uuid: 'AGO-PPD-F', source: 'demo' },
    ['cfdi-AGO-PPD-F'],
  ),
  txn(
    '2026-08-15',
    'TecnoStore SA de CV',
    'Equipo de cómputo',
    [
      { account: 'Assets:FixedAssets:Equipo', amount: mx('20000.00') },
      { account: 'Assets:Taxes:IVA-Acreditable', amount: mx('3200.00') },
      { account: 'Assets:Bank:BBVA', amount: mx('-23200.00') },
    ],
    { cfdi_uuid: 'REC-AGO-3', source: 'demo' },
    ['cfdi-REC-AGO-3'],
  ),
  txn(
    '2026-08-15',
    null,
    'Deposito En Efectivo Ventanilla',
    [
      { account: 'Assets:Bank:BBVA', amount: mx('6500.00') },
      { account: 'Income:Other', amount: mx('-6500.00') },
    ],
    { review: 'deposit_without_cfdi', source: 'demo-bank' },
    ['bank-2026-08-15-deposito'],
  ),
  txn(
    '2026-08-18',
    'Cliente Alfa SA de CV',
    'Soporte mensual — agosto',
    [
      { account: 'Assets:Receivable:Clients', amount: mx('13920.00') },
      { account: 'Income:Freelance', amount: mx('-12000.00') },
      { account: 'Liabilities:Taxes:IVA-Trasladado', amount: mx('-1920.00') },
    ],
    { cfdi_uuid: 'AGO-PUE-E', source: 'demo' },
    ['cfdi-AGO-PUE-E'],
  ),
];

export const BALANCES: Record<string, Amount[]> = {
  'Assets:Bank:BBVA': [mx('123217.50')],
  'Assets:Cash': [mx('3840.00')],
  'Assets:FixedAssets:Equipo': [mx('20000.00')],
  'Assets:Receivable:Clients': [mx('23200.00')],
  'Assets:Taxes:ISR-Retenido': [mx('562.50')],
  'Assets:Taxes:IVA-Acreditable': [mx('5120.00')],
  'Equity:Opening': [mx('-55000.00')],
  'Expenses:Food:Restaurants': [mx('1160.00')],
  'Expenses:Office': [mx('4000.00')],
  'Expenses:Software': [mx('8000.00')],
  'Income:Freelance': [mx('-110000.00')],
  'Income:Other': [mx('-6500.00')],
  'Liabilities:Taxes:IVA-Trasladado': [mx('-17600.00')],
};

export const ACCOUNTS = [
  'Assets:Bank:BBVA',
  'Assets:Bank:Banorte',
  'Assets:Bank:Nu',
  'Assets:Cash',
  'Assets:FixedAssets:Equipo',
  'Assets:Receivable:Clients',
  'Assets:Taxes:ISR-Retenido',
  'Assets:Taxes:IVA-Acreditable',
  'Equity:Opening',
  'Expenses:Food:Restaurants',
  'Expenses:Office',
  'Expenses:Software',
  'Income:Freelance',
  'Income:Other',
  'Liabilities:CreditCard:BBVA',
  'Liabilities:Loans:Auto',
  'Liabilities:Taxes:IVA-Trasladado',
];

export const BQL_ROWS: Record<string, string | number | null>[] = [
  { account: 'Assets:Bank:BBVA', 'sum(position)': '(123217.50 MXN)' },
  { account: 'Assets:Cash', 'sum(position)': '(3840.00 MXN)' },
  { account: 'Assets:FixedAssets:Equipo', 'sum(position)': '(20000.00 MXN)' },
];

/* ---------------------------------------------------------------------- pf */

export const ACCOUNTS_OVERVIEW: AccountsOverview = {
  groups: {
    bank: [{ account: 'Assets:Bank:BBVA', balances: [mx('123217.50')] }],
    cash: [{ account: 'Assets:Cash', balances: [mx('3840.00')] }],
    other_assets: [
      { account: 'Assets:FixedAssets:Equipo', balances: [mx('20000.00')] },
      { account: 'Assets:Receivable:Clients', balances: [mx('23200.00')] },
      { account: 'Assets:Taxes:ISR-Retenido', balances: [mx('562.50')] },
      { account: 'Assets:Taxes:IVA-Acreditable', balances: [mx('5120.00')] },
    ],
    other_liabilities: [{ account: 'Liabilities:Taxes:IVA-Trasladado', balances: [mx('-17600.00')] }],
  },
  net_worth: mx('193540.00'),
  net_worth_series: [
    { month: '2025-10', net_worth: '0' },
    { month: '2025-11', net_worth: '0' },
    { month: '2025-12', net_worth: '0' },
    { month: '2026-01', net_worth: '0' },
    { month: '2026-02', net_worth: '0' },
    { month: '2026-03', net_worth: '0' },
    { month: '2026-04', net_worth: '0' },
    { month: '2026-05', net_worth: '0' },
    { month: '2026-06', net_worth: '0' },
    { month: '2026-07', net_worth: '82000.00' },
    { month: '2026-08', net_worth: '193540.00' },
  ],
  explain: explain(
    'Net worth = sum(Assets) − sum(Liabilities) across all currencies as booked.',
    [{ label: 'net_worth', formula: 'sum(Assets) - sum(Liabilities)', value: '193540.00' }],
    [],
    [],
  ),
};

export const INCOME: IncomeOverview = {
  months: [
    {
      month: '2026-07',
      gross: mx('45000.00'),
      retained: mx('640.00'),
      net: mx('44360.00'),
      by_source: { 'Income:Freelance': '45000.00' },
      expected_vs_received: { issued: '17400.00', pending_ppd_without_rep: '0', count: 2 },
    },
    {
      month: '2026-08',
      gross: mx('51500.00'),
      retained: mx('4312.50'),
      net: mx('47187.50'),
      by_source: { 'Income:Freelance': '45000.00', 'Income:Other': '6500.00' },
      expected_vs_received: { issued: '52200.00', pending_ppd_without_rep: '9280.00', count: 3 },
    },
    {
      month: '2026-09',
      gross: mx('0'),
      retained: mx('0'),
      net: mx('0'),
      by_source: {},
      expected_vs_received: { issued: '0', pending_ppd_without_rep: '0', count: 0 },
    },
  ],
  sources: [
    { account: 'Income:Freelance', months: { '2026-07': '45000.00', '2026-08': '45000.00' } },
    { account: 'Income:Other', months: { '2026-08': '6500.00' } },
  ],
  smoothed_average: mx('32166.67'),
  explain: explain(
    'Irregular-income 6-month average is the mean of gross income over the last 3 months.',
    [{ label: 'average', formula: 'sum(gross)/3', value: '32166.66666666666666666666667' }],
    [],
    [],
  ),
};

export const LABELS: Labels = [
  {
    id: 'lbl-569885caff5c',
    ws_id: WS_ID,
    name: 'Comida fuera',
    aliases: ['restaurante', 'comida'],
    account: 'Expenses:Food:DiningOut',
    icon: '🍽️',
    tax: {
      MX: { isr_deductible: false, iva_creditable: false, requires_cfdi: false, personal_deduction: false },
      US: { schedule_c: false, itemized: false },
    },
    sort: 0,
    kind: 'expense',
    archived: false,
  },
  {
    id: 'lbl-6c72269a8eab',
    ws_id: WS_ID,
    name: 'Súper',
    aliases: ['super', 'supermercado', 'abarrotes'],
    account: 'Expenses:Food:Groceries',
    icon: '🛒',
    tax: {
      MX: { isr_deductible: false, iva_creditable: false, requires_cfdi: false, personal_deduction: false },
      US: { schedule_c: false, itemized: false },
    },
    sort: 1,
    kind: 'expense',
    archived: false,
  },
  {
    id: 'lbl-d92e338efc65',
    ws_id: WS_ID,
    name: 'Renta/Hipoteca',
    aliases: ['renta', 'hipoteca', 'infonavit'],
    account: 'Expenses:Housing:RentMortgage',
    icon: '🏠',
    tax: {
      MX: { isr_deductible: false, iva_creditable: false, requires_cfdi: false, personal_deduction: false },
      US: { schedule_c: false, itemized: false },
    },
    sort: 2,
    kind: 'expense',
    archived: false,
  },
  {
    id: 'lbl-office',
    ws_id: WS_ID,
    name: 'Oficina',
    aliases: ['oficina', 'renta oficina'],
    account: 'Expenses:Office',
    icon: '🏢',
    tax: {
      MX: { isr_deductible: false, iva_creditable: true, requires_cfdi: true, personal_deduction: false },
      US: { schedule_c: true, itemized: false },
    },
    sort: 3,
    kind: 'expense',
    archived: false,
  },
  {
    id: 'lbl-software',
    ws_id: WS_ID,
    name: 'Software',
    aliases: ['software', 'suscripciones'],
    account: 'Expenses:Software',
    icon: '💻',
    tax: {
      MX: { isr_deductible: false, iva_creditable: true, requires_cfdi: true, personal_deduction: false },
      US: { schedule_c: true, itemized: false },
    },
    sort: 4,
    kind: 'expense',
    archived: false,
  },
  // Income category seeds (added idempotently by name on the server).
  ...[
    ['lbl-inc-salary', 'Sueldo/Nómina', 'Income:Salary', '💼', ['nomina', 'sueldo', 'quincena']],
    ['lbl-inc-rent', 'Renta cobrada', 'Income:Rent', '🏘️', ['renta cobrada']],
    ['lbl-inc-interest', 'Intereses', 'Income:Interest', '🏦', ['intereses']],
    ['lbl-inc-dividends', 'Dividendos', 'Income:Dividends', '📈', ['dividendos']],
    ['lbl-inc-other', 'Otros ingresos', 'Income:Other', '💰', ['otros ingresos']],
  ].map(([id, name, account, icon, aliases], n) => ({
    id: id as string,
    ws_id: WS_ID,
    name: name as string,
    aliases: aliases as string[],
    account: account as string,
    icon: icon as string,
    tax: {},
    sort: 100 + n,
    kind: 'income' as const,
    archived: false,
  })),
];

export const BUDGETS: Budget[] = [
  { id: 'bud-9ab50bc41d0c', ws_id: WS_ID, label_id: 'lbl-569885caff5c', period: '2026-08', amount: '3500', currency: 'MXN', rollover: true },
  { id: 'bud-5b45b312b2d4', ws_id: WS_ID, label_id: 'lbl-6c72269a8eab', period: '2026-08', amount: '6000', currency: 'MXN', rollover: true },
];

export const BUDGETS_STATUS = {
  period: '2026-08',
  budgets: [
    {
      budget_id: 'bud-9ab50bc41d0c',
      label_id: 'lbl-569885caff5c',
      label_name: 'Comida fuera',
      account: 'Expenses:Food:DiningOut',
      budget: mx('3500'),
      rollover_applied: '0',
      spent: mx('0'),
      remaining: mx('3500'),
      pct: '0.0000',
      alert: 'none' as const,
      deductible_share: mx('0'),
      explain: explain(
        'Comida fuera: spent / (budget + rollover).',
        [
          { label: 'effective_budget', formula: 'amount + rollover', value: '3500' },
          { label: 'spent', formula: null, value: '0' },
          { label: 'remaining', formula: 'effective_budget - spent', value: '3500' },
        ],
        [],
        [],
      ),
    },
    {
      budget_id: 'bud-5b45b312b2d4',
      label_id: 'lbl-6c72269a8eab',
      label_name: 'Súper',
      account: 'Expenses:Food:Groceries',
      budget: mx('6000'),
      rollover_applied: '0',
      spent: mx('0'),
      remaining: mx('6000'),
      pct: '0.0000',
      alert: 'none' as const,
      deductible_share: mx('0'),
      explain: explain(
        'Súper: spent / (budget + rollover).',
        [
          { label: 'effective_budget', formula: 'amount + rollover', value: '6000' },
          { label: 'spent', formula: null, value: '0' },
          { label: 'remaining', formula: 'effective_budget - spent', value: '6000' },
        ],
        [],
        [],
      ),
    },
  ],
  safe_to_spend: mx('9500'),
};

export const GOALS: Goals = [
  {
    id: 'goal-ad79e9f36e53',
    ws_id: WS_ID,
    kind: 'emergency',
    name: 'Fondo de emergencia',
    target: '90000',
    currency: 'MXN',
    target_date: '2027-06-30',
    account: 'Assets:Bank:Nu',
    created_at: '2026-09-05T20:45:12.007331+00:00',
    progress: mx('0'),
    remaining: mx('90000'),
    monthly_required: mx('10000.00'),
    explain: explain(
      'monthly_required = (target − progress) / months remaining to target_date.',
      [
        { label: 'months_left', formula: null, value: '9' },
        { label: 'monthly_required', formula: '(target - progress) / months_left', value: '10000.00' },
      ],
      [],
      [],
    ),
    months_of_spend_covered: '0.00',
  },
  {
    id: 'goal-38e980badbed',
    ws_id: WS_ID,
    kind: 'purchase',
    name: 'Laptop nueva',
    target: '35000',
    currency: 'MXN',
    target_date: '2026-12-31',
    account: 'Assets:Bank:Banorte',
    created_at: '2026-09-05T20:45:12.017826+00:00',
    progress: mx('0'),
    remaining: mx('35000'),
    monthly_required: mx('11666.67'),
    explain: explain(
      'monthly_required = (target − progress) / months remaining to target_date.',
      [
        { label: 'months_left', formula: null, value: '3' },
        { label: 'monthly_required', formula: '(target - progress) / months_left', value: '11666.67' },
      ],
      [],
      [],
    ),
  },
];

export const GOAL_PROJECTIONS: Record<string, { month: string; balance: string }[]> = {
  'goal-ad79e9f36e53': [
    { month: '2026-10', balance: '10000.00' },
    { month: '2026-11', balance: '20000.00' },
    { month: '2026-12', balance: '30000.00' },
    { month: '2027-01', balance: '40000.00' },
    { month: '2027-02', balance: '50000.00' },
    { month: '2027-03', balance: '60000.00' },
    { month: '2027-04', balance: '70000.00' },
    { month: '2027-05', balance: '80000.00' },
    { month: '2027-06', balance: '90000.00' },
  ],
};

export const CARDS: Cards = [
  {
    id: 'card-6d442896fd44',
    name: 'BBVA Azul',
    account: 'Liabilities:CreditCard:BBVA',
    balance: mx('0'),
    limit: mx('60000'),
    utilization: '0.0000',
    next_cut_date: '2026-09-20',
    next_due_date: '2026-09-10',
    pago_no_intereses: mx('0'),
    minimum_payment_note: "(verify) minimum payment is set by the issuer's cardholder agreement",
    msi: [],
    explain: explain(
      "Pago para no generar intereses = statement (cut-date) balance in full; minimum payment is a card-issuer policy, not computed here (verify with your card agreement).",
      [
        { label: 'balance', formula: null, value: '0' },
        { label: 'utilization', formula: '|balance| / limit', value: '0.0000' },
      ],
      [],
      [],
    ),
  },
];

export const LOANS: Loans = [
  {
    id: 'loan-b0529662e3e1',
    ws_id: WS_ID,
    account: 'Liabilities:Loans:Auto',
    name: 'Crédito auto',
    principal: '180000',
    currency: 'MXN',
    annual_rate: '0.14',
    months: 48,
    start: '2026-01-15',
  },
];

export const REVIEW: Record<string, MonthlyReview> = {
  '2026-08': {
    period: '2026-08',
    income: mx('51500.00'),
    expense: mx('6160.00'),
    net: mx('45340.00'),
    vs_previous_month: { income_delta: '6500.00', expense_delta: '2160.00' },
    top_labels: [
      { label: 'Expenses:Software', amount: '5000.00' },
      { label: 'Expenses:Food:Restaurants', amount: '1160.00' },
    ],
    anomalies: [],
    goals_progress: GOALS,
    upcoming_bills: [],
    interest_paid: mx('0'),
    explain: explain(
      'Monthly review aggregates ledger postings for the period; deltas vs. prior month.',
      [
        { label: 'income', formula: null, value: '51500.00' },
        { label: 'expense', formula: null, value: '6160.00' },
        { label: 'net', formula: 'income - expense', value: '45340.00' },
      ],
      [],
      [],
    ),
  },
};

export const RECURRING: RecurringOverview = {
  bills: [],
  explain: explain(
    'Recurring bills detected from same payee, similar amount (±15%), 20-40 day cadence.',
    [],
    [],
    [],
  ),
};

/* ------------------------------------------------------------------- inbox */

export const INBOX_SEED: InboxItem[] = [
  {
    id: 'inbox-c9a8f78fbb6e',
    ws_id: WS_ID,
    kind: 'quickadd',
    status: 'pending',
    proposed: {
      date: '2026-09-05',
      payee: 'tacos',
      narration: '250 tacos comida',
      postings: [
        { account: 'Assets:Cash', amount: mx('-250') },
        { account: 'Expenses:Food:DiningOut', amount: null },
      ],
      tags: [],
      links: [],
      meta: { source: 'quickadd', raw_text: '250 tacos comida', label: 'Comida fuera' },
    },
    confidence: 0.9,
    source_ref: null,
    created_at: '2026-09-05T20:45:14.020039Z',
    decided_at: null,
    warnings: [],
  },
];

/* ---------------------------------------------------------------- satsync */

export const VAULT: VaultStatus = { present: false };

export const JOBS: SyncJobs = [];

/* --------------------------------------------------------------- research */
/* not yet checked against a real API response — no sample exists for /research/ask */

export const RESEARCH_ANSWERS: { match: RegExp; answer: ResearchAnswer }[] = [
  {
    match: /iva|laptop|comput|acredit/i,
    answer: {
      answer:
        'Sí, siempre que se cumplan los cuatro requisitos del artículo 5 de la LIVA: que el bien sea estrictamente indispensable para tu actividad, que el IVA conste por separado en el CFDI, que el comprobante esté a tu RFC y que el pago se haya hecho por un medio bancarizado cuando excede $2,000.00.',
      citations: [CITE_LIVA5, CITE_RMF],
      confidence: 0.86,
      abstained: false,
    },
  },
  {
    match: /isr|113|tasa|resico/i,
    answer: {
      answer:
        'En RESICO persona física el ISR mensual se calcula aplicando una tasa fija por tramo a la totalidad de los ingresos efectivamente cobrados en el mes, sin IVA y sin deducción alguna.',
      citations: [CITE_113E],
      confidence: 0.92,
      abstained: false,
    },
  },
];

export const RESEARCH_ABSTAIN: ResearchAnswer = {
  answer: '',
  citations: [],
  confidence: 0.12,
  abstained: true,
};

/* ------------------------------------------------------------------ watch */
/* not yet checked against a real API response — no sample exists for /watch/changes or /watch/run */

export const CHANGES: ChangesResponse = {
  changes: [
    {
      id: 'chg-2026-08-28-dof',
      source_id: 'dof-daily',
      detected_at: '2026-08-28T06:00:00+00:00',
      summary:
        'Segunda Resolución de Modificaciones a la RMF 2026: ajusta los plazos de emisión del complemento de pago (REP) y precisa la información precargada de la declaración mensual del RESICO.',
      domains: ['resico', 'cfdi'],
      diff_excerpt: null,
      corpus_source_id: null,
      effective_from: '2026-09-01',
    },
  ],
  proposals: [
    {
      id: 'prop-001',
      rule_id: 'mx.resico.income_cash_basis',
      from_version: '2026.1',
      to_version: '2026.2',
      rationale:
        'Ajustar el plazo de emisión del REP conforme a la RMF publicada el 2026-08-28; afecta el mes en que un PPD se reconoce como ingreso.',
      status: 'awaiting_review',
    },
  ],
};
