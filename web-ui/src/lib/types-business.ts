/**
 * Business, insights, reports and workflows wire types.
 *
 * The business / insights / reports shapes were read off a real response in
 * `web-ui/docs/api-samples.json` or off the router that produces it; the workflows shapes were
 * checked against the real API (see the workflows block of lib/api.ts).
 *
 * Money is always `{amount: str(Decimal), currency}`; ratios and day counts stay strings
 * whenever the API produced them with `Decimal`.
 */
import type { Amount, Citation, Explain, Jurisdiction, Lang, WorkspaceKind } from './types';

/* =========================================================== business */

/** A figure the business module returns: an Amount that carries its own Explain. */
export interface BizFigure extends Amount {
  explain: Explain;
}

export interface BizRatio {
  value: string | null;
  percent: string | null;
  explain: Explain;
}

export interface OpexGroup {
  group: string;
  amount: Amount;
}

export interface BizOpex {
  total: Amount;
  by_group: OpexGroup[];
  payroll: Amount;
  explain: Explain;
}

export interface BizRunway {
  months: string | null;
  average_burn: Amount;
  lookback_months: number;
  explain: Explain;
}

export interface BizTaxReserve {
  total: Amount;
  isr: Amount;
  iva: Amount;
  source: string;
  warnings: string[];
  explain: Explain;
}

/** GET /api/business/{ws}/kpis?period= */
export interface BusinessKpis {
  workspace: string;
  period: string;
  currency: string;
  revenue: BizFigure;
  cogs: BizFigure;
  gross_profit: BizFigure;
  gross_margin: BizRatio;
  operating_expenses: BizOpex;
  operating_profit: BizFigure;
  cash: BizFigure;
  receivables: BizFigure;
  payables: BizFigure;
  runway: BizRunway;
  tax_reserve: BizTaxReserve;
}

export interface AgingBucket {
  bucket: string;
  amount: Amount;
  invoices: number;
}

export interface OpenInvoice {
  uuid: string;
  fecha: string;
  client_rfc: string;
  metodo_pago: string;
  total: Amount;
  outstanding: Amount;
  age_days: number;
  bucket: string;
  reps: number;
}

export interface TopClient {
  client_rfc: string;
  invoices: number;
  issued: Amount;
  paid: Amount;
  outstanding: Amount;
}

/** GET /api/business/{ws}/invoices */
export interface InvoiceRegister {
  workspace: string;
  as_of: string;
  currency: string;
  period: { start: string | null; end: string | null };
  counts: { issued: number; open: number };
  issued: Amount;
  collected: Amount;
  outstanding: Amount;
  aging: AgingBucket[];
  open_invoices: OpenInvoice[];
  top_clients: TopClient[];
  dso_days: string | null;
  explain: Explain;
}

/** POST /api/business/{ws}/invoices/remind — returns text; Aurum never sends it. */
export interface InvoiceReminder {
  uuid: string;
  client_rfc: string;
  outstanding: Amount;
  age_days: number;
  bucket: string;
  paid: boolean;
  text: Record<Lang, string>;
  sent: boolean;
  note: string;
}

export interface Employee {
  id: string;
  name: string;
  rfc: string | null;
  daily_salary: Amount;
  sbc_daily: Amount;
  state: string;
  active: boolean;
  hired_on: string | null;
}

/** A row of GET /api/business/{ws}/payroll — stored run summary, amounts as bare strings. */
export interface PayrollRunSummary {
  id: string;
  period: string;
  days: string;
  currency: string;
  gross: string;
  net: string;
  isr_retenido: string;
  imss_employee: string;
  imss_employer: string;
  infonavit: string;
  isn: string;
  employer_cost: string;
  txn_id: string | null;
  created_at: string;
}

export interface ImssBranch {
  branch: string;
  amount: Amount;
  formula: string;
}

export interface PayrollLine {
  employee_id: string;
  name: string;
  rfc: string | null;
  state: string;
  days: string;
  gross: Amount;
  isr_retenido: Amount;
  isr_tarifa: Amount;
  subsidio_empleo: Amount;
  imss_employee: Amount;
  imss_employee_detail: Record<string, string>;
  imss_employer: Amount;
  imss_employer_branches: ImssBranch[];
  sbc_capped: boolean;
  infonavit: Amount;
  net: Amount;
  explain: Explain;
}

export type PayrollTotalKey =
  | 'gross'
  | 'net'
  | 'isr_retenido'
  | 'imss_employee'
  | 'imss_employer'
  | 'infonavit'
  | 'isn'
  | 'employer_cost';

/** POST /api/business/{ws}/payroll/run — nothing is filed; `status` is always "draft". */
export interface PayrollRun {
  id: string;
  workspace: string;
  period: string;
  days: string;
  currency: string;
  employees: number;
  lines: PayrollLine[];
  totals: Record<PayrollTotalKey, Amount>;
  isn: { value: Amount; explain: Explain };
  txn_id: string | null;
  status: string;
  warnings: string[];
  explain: Explain;
}

export interface BizConstant {
  key: string;
  value: string;
  citation: Citation;
  source_url: string | null;
  verified: boolean;
  verified_on: string | null;
  note: string | null;
}

/** GET /api/business/constants/mx-nl */
export interface BizConstants {
  year: number;
  verified_on: string;
  constants: BizConstant[];
  unverified: string[];
}

/* =========================================================== insights */

export type Severity = 'urgent' | 'warn' | 'info';

export interface InsightAction {
  label: string;
  href: string;
}

/** GET /api/insights/{ws}?period= */
export interface Insight {
  id: string;
  ws_id: string;
  kind: string;
  severity: Severity;
  title: string;
  body: string;
  amount: Amount | null;
  due_date: string | null;
  explain: Explain | null;
  actions: InsightAction[];
}

/** GET /api/insights/{ws}/calendar?from=&to= */
export interface CalendarEntry {
  kind: string;
  date: string;
  title: string;
  period?: string | null;
  note?: string | null;
}

/** GET /api/insights/{ws}/digest?format=json */
export interface Digest {
  workspace: string;
  period: string;
  text: string;
  urgent_count: number;
  insights: Insight[];
}

/* ============================================================ reports */

export interface ReportPack {
  pack: string;
  title: Record<Lang, string>;
  applicable: boolean;
  period_kind: 'month' | 'year' | 'none';
  url: string;
}

/** GET /api/reports/{ws} */
export interface ReportCatalog {
  workspace: string;
  kind?: WorkspaceKind;
  jurisdictions?: Jurisdiction[];
  packs: ReportPack[];
  warnings?: string[];
}

export interface ReportKpi {
  label: string;
  value: string;
  note: string | null;
}

export interface ReportTable {
  title: string;
  columns: string[];
  rows: string[][];
}

/** The preview's explains carry only summary/steps/citations. */
export interface ReportExplain {
  summary: string;
  steps: { label: string; formula?: string | null; value: string }[];
  citations: Citation[];
}

export interface ReportSection {
  title: string;
  kpis: ReportKpi[];
  tables: ReportTable[];
  notes: string[];
  explains: ReportExplain[];
}

/** GET /api/reports/{ws}/{pack}/preview?period= */
export interface ReportPreview {
  title: string;
  workspace: string;
  period: string | null;
  lang: Lang;
  draft: boolean;
  watermark_text: string | null;
  generated_at: string;
  rule_versions: string[];
  sections: ReportSection[];
  warnings: string[];
}

/** POST/GET /api/reports/{ws}/{pack}/archive */
export interface ArchivedReport {
  id: string;
  ws_id?: string;
  workspace?: string;
  pack: string;
  period: string | null;
  format: string;
  path: string;
  sha256: string;
  created_at: string;
  size?: number;
}

/* ========================================================== workflows */
/* Verified against the real API (2026-09): GET /api/workflows/{ws} returns a bare list of
   summaries (no yaml/builtin), the detail endpoint carries the yaml + parsed definition,
   and a run trace reports one entry per step with an HTTP status/duration/excerpt. */

/** One entry of GET /api/workflows/{ws} — a summary only, no yaml. */
export interface WorkflowSummary {
  id: string;
  workspace: string;
  name: string;
  schedule: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface WorkflowStepDef {
  id: string;
  method: string;
  path: string;
  body?: unknown;
  when?: string | null;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string | null;
  schedule?: string | null;
  steps: WorkflowStepDef[];
}

/** GET /api/workflows/{ws}/{id} */
export interface WorkflowDetail {
  workspace: string;
  id: string;
  yaml: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
  definition: WorkflowDefinition | null;
}

/** One entry of a run's `steps` (POST …/run or GET …/runs/{run_id}). */
export interface WorkflowRunStep {
  run_id: string;
  step_index: number;
  step_id: string;
  method: string;
  path: string;
  status_code: number | null;
  duration_ms: number;
  response_excerpt?: string | null;
  error?: string | null;
}

/** POST /api/workflows/{ws}/{id}/run · GET …/runs/{run_id} */
export interface WorkflowRun {
  id: string;
  workspace: string;
  workflow_id: string;
  started_at: string;
  finished_at: string | null;
  status: string; // "success" | "failed" — kept loose so an unknown status still renders
  error: string | null;
  steps: WorkflowRunStep[];
}

/** One entry of GET /api/workflows/{ws}/{id}/runs — no `steps`; params is a JSON string. */
export interface WorkflowRunSummary {
  id: string;
  ws_id: string;
  workflow_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  params: string | null;
  error: string | null;
}

/** POST|DELETE /api/workflows/{ws}/{id}/schedule — `gated` means the scheduler thread is
    off on the server (AURUM_WORKFLOWS_SCHEDULER=1 turns it on); the cron is still saved. */
export interface WorkflowScheduleResult {
  workspace: string;
  id: string;
  schedule: string | null;
  gated: boolean;
}

/** POST /api/workflows/{ws}/propose — an LLM draft; never saved, never run. */
export interface WorkflowProposal {
  workspace: string;
  source: string; // "offline-fallback" | "llm"
  yaml: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/** GET /api/workflows/catalog — the endpoints a workflow step may call. */
export interface WorkflowCatalogEntry {
  method: string;
  path: string;
  summary: string;
}

export interface WorkflowCatalog {
  endpoints: WorkflowCatalogEntry[];
}
