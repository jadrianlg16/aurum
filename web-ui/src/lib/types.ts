/**
 * Wire types — mirrors the REAL API responses captured live against the `demo-mx` workspace in
 * `web-ui/docs/api-samples.json` (27 endpoints, arrays trimmed to 3 items). Where an envelope
 * might be expected (`{ workspaces: [...] }`, `JournalResponse`, etc.) but the real API does
 * not send one, the type here is the bare shape the API actually returns — usually a bare array.
 *
 * Money rule ("Money is Decimal", docs/ARCHITECTURE.md): amounts arrive as
 * `{amount: string, currency}` where `amount` is a str(Decimal). The UI NEVER parses one to a float for arithmetic; it formats for display
 * (see lib/format.ts) and lets the API do the math. Some endpoints return a *bare* decimal
 * string field (no currency alongside it, or currency as a separate field) — those are typed as
 * `DecimalString`, still never parsed to a float for arithmetic.
 */

/* --------------------------------------------------------------------- core */

import type { PfAccount } from './types-personal';

export interface Amount {
  amount: string;
  currency: string;
}

/** A str(Decimal) that arrives without a paired currency field (ratio, rate, bare amount). */
export type DecimalString = string;

export type TrustTier = 'primary' | 'official_guidance' | 'professional' | 'blog';

export interface Citation {
  law: string;
  article: string;
  url?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  trust_tier: TrustTier;
  excerpt?: string | null;
  /** Research graph layer: cross-references detected in the cited text. */
  related?: RelatedRef[] | null;
}

export interface Step {
  /** A stable id (`liquid_balance`, `buffer`, …) the UI maps to human labels. */
  id?: string;
  label: string;
  formula?: string | null;
  value: string;
}

export interface Explain {
  summary: string;
  steps: Step[];
  citations: Citation[];
  rule_versions: string[];
  confidence?: number | null;
}

export type WorkspaceKind = 'personal' | 'business' | 'advisory';
export type Jurisdiction = 'MX' | 'US';
export type Lang = 'es' | 'en';

export interface Workspace {
  id: string;
  name: string;
  kind: WorkspaceKind;
  jurisdictions: Jurisdiction[];
  base_currency: string;
  language: Lang;
  /** RFC/CURP arrive masked from the API; the UI never un-masks. */
  profile: Record<string, string | number | boolean | null>;
  created_at: string;
  /**
   * Personal is the product, so the shell hides tax/business/research and the
   * rest behind "Avanzado" unless this says otherwise. Optional because a workspace saved
   * before these fields existed has neither — `undefined` is read as `simple` / all-off.
   */
  ui_mode?: import('./types-personal').UiMode | null;
  modules?: import('./types-personal').Modules | null;
  /** `personal` is always protected (cannot be unset); hidden rows leave the list. */
  protected?: boolean;
  hidden?: boolean;
}

/** GET /api/health (`data_dir` dropped; `auth`, `bind`, `schema` added). */
export interface Health {
  ok: boolean;
  version: string;
  /** Older servers only. */
  data_dir?: string;
  llm: {
    provider: string;
    model: string;
    cloud_opt_in: boolean;
  };
  /** `AURUM_DEMO_MODE=1` makes the API read-only. Absent means "not in demo mode". */
  demo_mode?: boolean;
  /** @deprecated legacy flag; read `auth.required`. */
  auth_required?: boolean;
  auth?: { required: boolean; source: 'env' | 'file' | 'none' };
  bind?: string;
  /** `{module: version}` of the applied migrations. */
  schema?: Record<string, number>;
}

/** GET /api/ledger/{ws}/health. */
export interface LedgerHealth {
  txns: number;
  errors: { lineno: number; message: string }[];
  error_count: number;
}

/** POST /api/backup → the archive written under data/backups. */
export interface BackupResult {
  path: string;
  size: number;
  sha256: string;
}

/** GET /api/backups row. */
export interface BackupEntry {
  name: string;
  size: number;
  created_at: string;
}

/* ------------------------------------------------------------------- ledger */

export interface Posting {
  account: string;
  amount?: Amount | null;
}

export interface Transaction {
  date: string;
  payee?: string | null;
  narration: string;
  postings: Posting[];
  tags: string[];
  links: string[];
  meta: Record<string, string>;
}

/** GET /api/ledger/{ws}/journal — a bare array, not `{ transactions: [...] }`. */
export type Journal = Transaction[];

/** GET /api/ledger/{ws}/balances — account -> amounts (an account can hold several commodities). */
export type Balances = Record<string, Amount[]>;

/** GET /api/ledger/{ws}/accounts — a bare array of account names. */
export type LedgerAccounts = string[];

/** POST /api/ledger/{ws}/query — beanquery rows; keys and value shapes are query-dependent. */
export type QueryRow = Record<string, string | number | null>;
export type QueryRows = QueryRow[];

/* -------------------------------------------------------------------- rules */

export interface RuleInfo {
  id: string;
  version: string;
  /** `${id}@${version}` — the identifier `rule_versions` arrays elsewhere reference. */
  rule_version: string;
  jurisdiction: string;
  effective_from: string;
  effective_to?: string | null;
  citation: Citation;
  doc: string;
}

/** GET /api/rules — a bare array. */
export type Rules = RuleInfo[];

export interface RuleResult {
  value: Amount;
  explain: Explain;
}

/* ---------------------------------------------------------------------- tax */

export type DiffKind =
  | 'pue_not_collected'
  | 'ppd_missing_rep'
  | 'deposit_without_cfdi'
  | 'cash_paid_expense'
  | 'fixed_asset_iva';

export interface PrefillDiff {
  kind: DiffKind;
  amount: Amount;
  documents: string[];
  explain: Explain;
}

export interface MonthCloseIncome {
  collected: Amount;
  by_rule: { rule: string; value: Amount }[];
  explain: Explain;
}

export interface ValueWithExplain {
  value: Amount;
  explain: Explain;
}

export interface MonthCloseIva {
  trasladado: Amount;
  acreditable: Amount;
  payable: Amount;
  explain: Explain;
}

export interface PrefillExpected {
  income: Amount;
  isr: Amount;
  iva_acreditable: Amount;
  explain: Explain;
}

export interface MonthClose {
  period: string;
  workspace: string;
  currency: string;
  income: MonthCloseIncome;
  isr: ValueWithExplain;
  iva: MonthCloseIva;
  retentions: { isr: Amount; iva: Amount };
  prefill_expected: PrefillExpected;
  diffs: PrefillDiff[];
  deadline: string;
  status: string;
  warnings: string[];
}

/* ------------------------------------------------------------------- ingest */

export type CfdiTipo = 'I' | 'E' | 'P' | 'N' | 'T';
export type MetodoPago = 'PUE' | 'PPD';
export type CfdiDirection = 'emitido' | 'recibido';

export interface Pago {
  fecha_pago: string;
  monto: string;
  uuid_relacionado: string;
  moneda?: string;
}

export interface CFDI {
  uuid: string;
  version: string;
  tipo: CfdiTipo;
  fecha: string;
  emisor_rfc: string;
  emisor_nombre?: string | null;
  receptor_rfc: string;
  receptor_nombre?: string | null;
  subtotal: string;
  total: string;
  moneda: string;
  metodo_pago?: MetodoPago | null;
  forma_pago?: string | null;
  uso_cfdi?: string | null;
  impuestos_trasladados: string;
  impuestos_retenidos: string;
  isr_retenido?: string;
  iva_retenido?: string;
  iva_trasladado: string;
  conceptos: Record<string, string | number>[];
  pagos: Pago[];
  direction: CfdiDirection;
  raw_path?: string | null;
}

/** GET /api/ingest/{ws}/cfdi — a bare array, not `{ cfdis: [...] }`. */
export type CfdiList = CFDI[];

export type InboxKind = 'quickadd' | 'cfdi' | 'bank' | 'photo';
export type InboxStatus = 'pending' | 'accepted' | 'rejected';

export interface InboxItem {
  id: string;
  ws_id: string;
  kind: InboxKind;
  status: InboxStatus;
  proposed: Transaction;
  confidence: number;
  source_ref?: string | null;
  created_at: string;
  decided_at?: string | null;
  warnings?: string[];
}

/** GET /api/ingest/{ws}/inbox — a bare array, not `{ items: [...] }`. */
export type InboxList = InboxItem[];

export interface UploadResult {
  accepted: number;
  inbox_items: string[];
  warnings: string[];
}

/* ------------------------------------------------------------------ satsync */

/**
 * GET /api/satsync/{ws}/vault — the only field the real API has shown is `present`. Its shape
 * when a vault IS configured (fingerprint, stored_at, etc.) is not yet checked against the real API.
 */
export interface VaultStatus {
  present: boolean;
  /** not yet checked against a real API response — no sample has present: true */
  stored_at?: string | null;
  /** not yet checked against a real API response — no sample has present: true */
  cer_fingerprint?: string | null;
}

export interface SyncJob {
  id: string;
  kind: string;
  status: string;
  requested_at: string;
  packages: number;
}

/** GET /api/satsync/{ws}/jobs — a bare array, not `{ jobs: [...] }`. */
export type SyncJobs = SyncJob[];

/* ----------------------------------------------------------------------- pf */

export interface LabelTaxMX {
  isr_deductible: boolean;
  iva_creditable: boolean;
  requires_cfdi: boolean;
  personal_deduction: boolean;
}

export interface LabelTaxUS {
  schedule_c: boolean;
  itemized: boolean;
}

/** `transfer` only exists for backfilled `Assets:` labels and is hidden from pickers. */
export type LabelKind = 'expense' | 'income' | 'transfer';

export interface Label {
  id: string;
  ws_id: string;
  name: string;
  aliases: string[];
  account: string;
  icon?: string | null;
  tax: { MX?: LabelTaxMX; US?: LabelTaxUS };
  sort: number;
  /** Optional only because an older server omits them. */
  kind?: LabelKind;
  archived?: boolean;
  parent?: string | null;
}

/** POST /labels: the server derives `Expenses:<Slug>` / `Income:<Slug>`. */
export interface LabelCreate {
  name: string;
  kind: Exclude<LabelKind, 'transfer'>;
  parent?: string | null;
  icon?: string | null;
  aliases?: string[];
  /** Advanced mode only — a ledger account typed by hand. */
  account?: string;
}

/** PUT /labels/{id}. */
export interface LabelPatch {
  name?: string;
  icon?: string | null;
  aliases?: string[];
  archived?: boolean;
}

/** GET /api/pf/{ws}/labels — a bare array, not `{ labels: [...] }`. */
export type Labels = Label[];

export interface AccountRow {
  account: string;
  balances: Amount[];
}

export interface AccountGroups {
  bank: AccountRow[];
  cash: AccountRow[];
  other_assets: AccountRow[];
  other_liabilities: AccountRow[];
}

export interface NetWorthPoint {
  month: string;
  net_worth: DecimalString;
}

/** GET /api/pf/{ws}/accounts */
export interface AccountsOverview {
  /** The flat pf_accounts rows the server also sends (aurum/pf/accounts.py get_accounts). */
  accounts?: PfAccount[];
  groups: AccountGroups;
  net_worth: Amount;
  net_worth_series: NetWorthPoint[];
  explain: Explain;
}

export interface IncomeExpectedVsReceived {
  issued: DecimalString;
  pending_ppd_without_rep: DecimalString;
  count: number;
}

export interface IncomeMonth {
  month: string;
  gross: Amount;
  retained: Amount;
  net: Amount;
  by_source: Record<string, DecimalString>;
  expected_vs_received: IncomeExpectedVsReceived;
}

export interface IncomeSourceHistory {
  account: string;
  months: Record<string, DecimalString>;
}

/** GET /api/pf/{ws}/income */
export interface IncomeOverview {
  months: IncomeMonth[];
  sources: IncomeSourceHistory[];
  smoothed_average: Amount;
  explain: Explain;
}

export interface Budget {
  id: string;
  ws_id: string;
  label_id: string;
  period: string;
  amount: DecimalString;
  currency: string;
  rollover: boolean;
}

/** GET /api/pf/{ws}/budgets — a bare array of `Budget`. */
export type Budgets = Budget[];

/**
 * One row of GET /budgets/status. Current shape (`carried`, `effective`, `state`, numeric
 * `pct`) plus the older fields (`alert`, `rollover_applied`, `explain`) kept optional so both
 * servers parse.
 */
export interface BudgetStatusRow {
  budget_id: string;
  label_id: string;
  label_name: string;
  icon?: string | null;
  account?: string;
  budget: Amount;
  carried?: Amount;
  effective?: Amount;
  spent: Amount;
  remaining: Amount;
  /** A number (percent); older servers sent a str(Decimal) ratio. */
  pct: number | DecimalString;
  state?: 'ok' | 'warn' | 'over';
  rollover?: boolean;
  /** @deprecated older field; derive from `state`. */
  alert?: 'none' | 'warn80' | 'over100';
  /** @deprecated older field; read `carried`. */
  rollover_applied?: DecimalString;
  deductible_share?: Amount | null;
  explain?: Explain;
}

/** @deprecated the row is `BudgetStatusRow`; this alias keeps older consumers typed. */
export type BudgetStatus = BudgetStatusRow;

/** GET /api/pf/{ws}/budgets/status. `safe_to_spend` is compat: label it 'Presupuesto restante'. */
export interface BudgetsStatus {
  period: string;
  currency?: string;
  budgets: BudgetStatusRow[];
  totals?: { budget: Amount; spent: Amount; remaining: Amount };
  has_previous?: boolean;
  previous_period?: string | null;
  safe_to_spend: Amount;
  explain?: Explain;
}

/** POST /budgets/copy → counts (idempotent). */
export interface BudgetsCopyResult {
  created: number;
  skipped: number;
  period: string;
}

export type GoalKind = 'savings' | 'emergency' | 'debt' | 'purchase';

export interface Goal {
  id: string;
  ws_id: string;
  kind: GoalKind;
  name: string;
  target: DecimalString;
  currency: string;
  target_date?: string | null;
  account: string;
  /** The pf account the goal is funded from; `account` is derived from it. */
  account_id?: string | null;
  account_name?: string | null;
  created_at: string;
  progress: Amount;
  remaining: Amount;
  /** Percent complete (a number on the current server, str(Decimal) on older ones). */
  pct?: number | DecimalString;
  monthly_required?: Amount | null;
  target_date_invalid?: boolean;
  explain: Explain;
  /** Only present on some goal kinds (e.g. emergency fund). */
  months_of_spend_covered?: DecimalString;
}

/** POST /goals: `account_id` preferred; `account` only in advanced mode. */
export interface GoalCreate {
  kind: GoalKind;
  name: string;
  target: Amount | DecimalString;
  target_date?: string | null;
  account_id?: string | null;
  account?: string;
  currency?: string;
}

/** GET /api/pf/{ws}/goals — a bare array, not `{ goals: [...] }`. */
export type Goals = Goal[];

export interface GoalProjectionPoint {
  month: string;
  balance: DecimalString;
}

/** GET /api/pf/{ws}/goals/{id}/projection */
export interface GoalProjection {
  goal_id: string;
  path: GoalProjectionPoint[];
  explain: Explain;
}

export interface MsiPlan {
  description: string;
  months_total: number;
  months_left: number;
  monthly: Amount;
  remaining: Amount;
}

export interface CreditCard {
  id: string;
  name: string;
  account: string;
  balance: Amount;
  limit: Amount;
  /** "0.0000" str(Decimal) ratio. */
  utilization: DecimalString;
  next_cut_date: string;
  next_due_date: string;
  /** "pago para no generar intereses" — statement balance in full. */
  pago_no_intereses: Amount;
  /** The API does not compute a minimum payment (issuer policy); this is an explanatory note. */
  minimum_payment_note: string;
  msi: MsiPlan[];
  explain: Explain;
}

/** GET /api/pf/{ws}/credit/cards — a bare array, not `{ cards: [...] }`. */
export type Cards = CreditCard[];

export interface Loan {
  id: string;
  ws_id: string;
  account: string;
  name: string;
  principal: DecimalString;
  currency: string;
  annual_rate: DecimalString;
  months: number;
  start: string;
}

/** GET /api/pf/{ws}/credit/loans — a bare array, not `{ loans: [...] }`. */
export type Loans = Loan[];

export interface AmortRow {
  month: number;
  payment: DecimalString;
  interest: DecimalString;
  principal: DecimalString;
  balance: DecimalString;
}

/** GET /api/pf/{ws}/credit/loans/{id}/amortization */
export interface Amortization {
  loan_id: string;
  payment: DecimalString;
  total_paid: DecimalString;
  total_interest: DecimalString;
  rows: AmortRow[];
  explain: Explain;
}

/** POST /api/pf/{ws}/credit/loans/{id}/whatif */
export interface LoanWhatIf {
  loan_id: string;
  months_to_payoff: number;
  months_saved: number;
  new_total_interest: DecimalString;
  interest_saved: Amount;
  explain: Explain;
}

export interface ReviewLabelRow {
  label: string;
  amount: DecimalString;
}

/** GET /api/pf/{ws}/review/{period} */
export interface MonthlyReview {
  period: string;
  income: Amount;
  expense: Amount;
  net: Amount;
  vs_previous_month: { income_delta: DecimalString; expense_delta: DecimalString };
  /** base_currency of the workspace (aurum/pf/review.py). */
  currency?: string;
  top_labels: ReviewLabelRow[];
  anomalies: unknown[];
  goals_progress: Goal[];
  upcoming_bills: unknown[];
  interest_paid: Amount;
  explain: Explain;
}

export interface RecurringBill {
  id: string;
  payee: string;
  amount: Amount;
  day: number;
  label: string;
  next_due: string;
}

/** GET /api/pf/{ws}/recurring */
export interface RecurringOverview {
  bills: RecurringBill[];
  explain: Explain;
}

/* ---------------------------------------------------- research / watch / mcp */
/* Not covered by api-samples.json — shapes below are assumed, unverified
   against the real API. */

/** not yet checked against a real API response */
export interface ResearchAnswer {
  answer: string;
  citations: Citation[];
  confidence: number;
  abstained: boolean;
}

/** not yet checked against a real API response */
export interface RuleProposal {
  id: string;
  rule_id: string;
  from_version: string;
  to_version: string;
  rationale: string;
  status: string;
}

/**
 * One detected law change — the flat row `GET /api/watch/changes` returns as a bare array, and
 * `GET /watch/sources/{id}/history` nests under `changes` (verified against the live API
 * 2026-09-25; the older `{source, title, published, status}` guess crashed the feed).
 */
export interface LawChange {
  id: string;
  source_id: string;
  detected_at: string;
  summary: string;
  domains: string[];
  diff_excerpt?: string | null;
  corpus_source_id?: string | null;
  effective_from?: string | null;
}

/** not yet checked against a real API response */
export interface ChangesResponse {
  changes: LawChange[];
  proposals: RuleProposal[];
}

/* ---------------------------------------------------------- UI-only shapes */

export interface Deadline {
  id: string;
  label: string;
  date: string;
  kind: 'tax' | 'card' | 'loan' | 'goal';
}

export interface McpTool {
  name: string;
  description: string;
}

/* ------------------------------------------------------------ write shapes */
/* Request bodies mirror the Pydantic models exactly (aurum/pf/*.py, aurum/ledger/base.py,
   aurum/core/workspaces.py): server-assigned fields (`id`, `ws_id`) are sent empty, and every
   money field is a decimal *string*. */

export interface GoalInput {
  id?: string;
  ws_id?: string;
  kind: GoalKind;
  name: string;
  target: DecimalString;
  currency: string;
  target_date?: string | null;
  account: string;
}

export interface BudgetInput {
  id?: string;
  ws_id?: string;
  label_id: string;
  period: string;
  amount: DecimalString;
  currency: string;
  rollover: boolean;
}

export interface CreditCardInput {
  id?: string;
  ws_id?: string;
  account: string;
  name: string;
  cut_day: number;
  due_day: number;
  limit_amount: DecimalString;
  currency: string;
  apr?: string | null;
}

export interface LoanInput {
  id?: string;
  ws_id?: string;
  account: string;
  name: string;
  principal: DecimalString;
  currency: string;
  annual_rate: DecimalString;
  months: number;
  start: string;
}

export interface MsiInput {
  id?: string;
  ws_id?: string;
  card_id: string;
  purchase: string;
  amount: DecimalString;
  currency: string;
  months: number;
  started: string;
  paid_months: number;
}

export interface CreditScore {
  id: string;
  ws_id: string;
  bureau: string;
  score: number;
  date: string;
}

export interface CreditScoreInput {
  id?: string;
  ws_id?: string;
  bureau: string;
  score: number;
  date: string;
}

/** GET /api/pf/{ws}/credit/scores — a bare array. */
export type CreditScores = CreditScore[];

export interface LabelInput {
  id?: string;
  ws_id?: string;
  name: string;
  aliases: string[];
  account: string;
  icon?: string | null;
  tax: { MX?: LabelTaxMX; US?: LabelTaxUS };
  sort: number;
}

/** POST /api/pf/{ws}/goals/{id}/whatif — body is `{extra_monthly}` (aurum/pf/goals.py WhatIf). */
export interface GoalWhatIf {
  /** 200 with `{error}` when the goal has no loan to simulate (aurum/pf/goals.py debt_whatif). */
  error?: string;
  goal_id?: string;
  months_to_payoff?: number;
  months_saved?: number;
  interest_saved?: Amount | null;
  explain: Explain;
}

/** POST /api/ledger/{ws}/transactions — the API returns the id it wrote. */
export interface TransactionResult {
  txn_id: string;
  warnings?: string[];
}

/* --------------------------------------------------------------- statements */

export interface StatementRow {
  account: string;
  label: string;
  amount: Amount;
}

export interface StatementSection {
  title: string;
  rows: StatementRow[];
  total: Amount;
}

export type StatementType = 'pnl' | 'balance' | 'cashflow';

/** GET /api/ledger/{ws}/statements/{period}?type=. */
export interface Statement {
  type: StatementType;
  period: string;
  currency: string;
  sections: StatementSection[];
  net: Amount;
  explain: Explain;
}

/* ---------------------------------------------------------------- reconcile */

export interface ReconcileSuggestion {
  txn_id?: string | null;
  cfdi_uuid?: string | null;
  score: number;
}

export interface ReconcileBankLine {
  id: string;
  date: string;
  description: string;
  amount: Amount;
  matched_txn_id?: string | null;
  cfdi_uuid?: string | null;
  suggestions: ReconcileSuggestion[];
}

/** GET /api/ingest/{ws}/reconcile?period=. */
export interface ReconcileBoard {
  bank_lines: ReconcileBankLine[];
  unmatched_bank: number;
  unmatched_cfdi: string[];
  explain: Explain;
}

export interface WorkspaceInput {
  id: string;
  name: string;
  kind: WorkspaceKind;
  jurisdictions: Jurisdiction[];
  base_currency: string;
  language: Lang;
  profile: Record<string, string | number | boolean | null>;
  ui_mode?: import('./types-personal').UiMode | null;
  modules?: import('./types-personal').Modules | null;
}

/* ===================================================================== */
/* US tax, cross-border, holdings, plan, credit report — shapes captured live in docs/api-samples.json */
/* ===================================================================== */

/* ------------------------------------------------------------- taxus (US) */

/** GET /api/tax/us/{ws}/{year} — every money field is an `Amount` the API produced. */
export interface UsScheduleC {
  gross_receipts: Amount;
  returns_and_allowances: Amount;
  cost_of_goods_sold: Amount;
  expenses: Amount;
  expenses_by_account: Record<string, Amount>;
  income_by_account: Record<string, Amount>;
  transactions: number;
  net: Amount;
  explain: Explain;
}

export interface UsSeTax {
  value: Amount;
  deductible_half: Amount;
  explain: Explain;
}

export interface UsIncomeTax {
  value: Amount;
  explain: Explain;
}

export interface UsQuarterly {
  due_dates: string[];
  amount_each: Amount;
  explain: Explain;
}

export interface UsTaxProfile {
  filing_status: string;
  entity_type: string;
  business_type: string;
  state: string;
}

export interface UsTaxYear {
  workspace: string;
  year: number;
  applicable: boolean;
  currency: string;
  profile: UsTaxProfile;
  schedule_c: UsScheduleC;
  se_tax: UsSeTax;
  income_tax: UsIncomeTax;
  total_tax: Amount;
  quarterly: UsQuarterly;
  organizer_url: string;
  tx_franchise_url: string;
  /** Constant keys the rules could not verify — rendered as `(verify)` chips. */
  unverified_constants: string[];
  warnings: string[];
  disclaimer: string;
  status?: string | null;
}

/** GET /api/tax/us/{ws}/{year}/tx-franchise */
export interface TxFranchise {
  workspace: string;
  year: number;
  applicable: boolean;
  currency: string;
  entity_type: string;
  business_type: string;
  total_revenue: Amount;
  no_tax_due_threshold: Amount;
  no_tax_due: boolean;
  tax: Amount;
  explain: Explain;
  warnings: string[];
  disclaimer: string;
}

/* -------------------------------------------------------- crossborder (XB) */

export interface XbIncomeSource {
  country: string;
  kind: string;
  /** decimal string */
  amount: string;
  currency: string;
}

export interface XbForeignAccount {
  country: string;
  institution?: string | null;
  /** decimal string */
  max_balance_usd: string;
}

/** PUT /api/crossborder/{ws}/profile body, and the `profile` block of the assessment. */
export interface CrossborderProfile {
  days_mx: number;
  days_us: number;
  days_us_prior_1: number;
  days_us_prior_2: number;
  days_abroad_for_feie: number;
  bona_fide_resident_abroad: boolean;
  home_mx: boolean;
  home_us: boolean;
  green_card: boolean;
  citizenship: string[];
  filing_status: string;
  main_professional_center?: string | null;
  /** decimal string */
  mx_source_income_share?: string | null;
  /** decimal string */
  foreign_tax_paid_usd?: string | null;
  income_sources: XbIncomeSource[];
  foreign_accounts: XbForeignAccount[];
  treaty_permanent_home?: string | null;
  treaty_center_of_vital_interests?: string | null;
  treaty_habitual_abode?: string | null;
  treaty_nationality?: string | null;
}

export interface XbTreatyStep {
  step: number;
  key: string;
  label: string;
}

export interface XbFeieOption {
  option: string;
  citation: string;
  value: Amount;
}

/** GET /api/crossborder/{ws}/assessment */
export interface CrossborderAssessment {
  workspace: string;
  profile: CrossborderProfile;
  residency: { mx: boolean; us: boolean; dual: boolean; weighted_us_days: Amount; explain: Explain };
  treaty: {
    applies: boolean;
    resolved_at_step?: number | null;
    checklist: XbTreatyStep[];
    explain: Explain;
  };
  fbar: { required: boolean; aggregate: Amount; threshold: string; explain: Explain };
  feie_vs_ftc: { options: XbFeieOption[]; explain: Explain };
  flags: string[];
  unverified_constants: string[];
  disclaimer: string;
}

/** PUT /api/crossborder/{ws}/profile response. */
export interface CrossborderProfileSaved {
  workspace: string;
  crossborder: CrossborderProfile;
}

/* ----------------------------------------------------------- holdings / fx */

export interface Position {
  symbol: string;
  account: string;
  /** decimal string */
  units: string;
  cost_basis: Amount;
  market_value?: Amount | null;
  unrealized_gain?: Amount | null;
  asset_class?: string | null;
  name?: string | null;
  price_as_of?: string | null;
}

export interface RealizedGain {
  symbol: string;
  date: string;
  /** decimal string */
  units: string;
  proceeds: Amount;
  cost_basis: Amount;
  gain: Amount;
  /** ISO date the lot was opened, when the API knows it. */
  acquired?: string | null;
}

export interface ContributionLimit {
  key: string;
  jurisdiction: Jurisdiction;
  label: string;
  limit: Amount;
  contributed: Amount;
  remaining: Amount;
  /** false renders a `(verify)` chip next to the figure. */
  verified: boolean;
}

export interface HoldingSymbol {
  ws_id: string;
  symbol: string;
  name?: string | null;
  asset_class?: string | null;
  currency: string;
}

/** GET /api/holdings/{ws} */
export interface HoldingsOverview {
  positions: Position[];
  realized_gains: RealizedGain[];
  allocation: { by_asset_class: Record<string, string>; total_market_value: string };
  explain: Explain;
  contributions: { year: number; limits: ContributionLimit[] };
  tax_explain: Explain;
  symbols: HoldingSymbol[];
}

export type TradeKind = 'buy' | 'sell' | 'dividend' | 'interest' | 'contribution';

/** POST /api/holdings/{ws}/trades body. `units` and `price.amount` are decimal strings. */
export interface TradeInput {
  date: string;
  account: string;
  symbol: string;
  kind: TradeKind;
  units: string;
  price: Amount;
  fees?: Amount | null;
  counter_account?: string | null;
  limit_key?: string | null;
}

export interface TradeResult {
  id: string;
  ws_id: string;
  date: string;
  account: string;
  symbol: string;
  kind: TradeKind;
  units: string;
  price_amount: string;
  price_currency: string;
  txn_id?: string | null;
  created_at: string;
}

/** POST /api/holdings/{ws}/prices body. */
export interface PriceInput {
  symbol: string;
  date: string;
  price: Amount;
}

/** GET /api/fx/rate — 404 (`FxRateNotFound`) when there is no token and no fixture. */
export interface FxRate {
  base: string;
  quote: string;
  date: string;
  /** decimal string */
  rate: string;
  source?: string | null;
}

/* ------------------------------------------------------------ creditreport */

export interface CreditReportAccount {
  grantor?: string | null;
  type?: string | null;
  limit?: string | null;
  balance?: string | null;
  status?: string | null;
  opened?: string | null;
}

export interface CreditReportScore {
  value: number | string;
  bureau?: string | null;
}

export interface CreditReportImport {
  id: string;
  ws_id: string;
  filename: string;
  imported_at: string;
  score?: CreditReportScore | null;
  accounts: CreditReportAccount[];
  warnings: string[];
}

/** GET /api/creditreport/{ws} */
export interface CreditReportState {
  imports: CreditReportImport[];
  latest: CreditReportImport | null;
}

/* --------------------------------------------------------------------- plan */

/** One JSON-schema property as the plan catalog emits it (flat, no `$ref`). */
export interface ScenarioField {
  type: 'string' | 'integer' | 'number' | 'boolean';
  title?: string;
  description?: string;
  default?: string | number | boolean;
  minimum?: number;
  maximum?: number;
}

export interface ScenarioSchema {
  title?: string;
  type: 'object';
  properties: Record<string, ScenarioField>;
}

/** GET /api/plan/{ws}/scenarios */
export interface ScenarioSpec {
  id: string;
  schema: ScenarioSchema;
  metric_path: string[];
}

export type ScenarioInputs = Record<string, string | number | boolean>;

/** POST /api/plan/{ws}/scenarios/{id}/run — `results` is scenario-shaped, so it stays loose. */
export interface ScenarioRun {
  inputs: ScenarioInputs;
  results: Record<string, unknown>;
  explain: Explain;
}

export interface SensitivityRow {
  field: string;
  /** decimal strings */
  low: string;
  base?: string | null;
  high: string;
  range: string;
}

/** POST .../sensitivity */
export interface SensitivityResult {
  metric_path: string[];
  rows: SensitivityRow[];
  explain?: Explain | null;
}

/** POST .../montecarlo */
export interface MonteCarloResult {
  inputs: ScenarioInputs;
  results: {
    p10: string;
    p50: string;
    p90: string;
    mean: string;
    success_rate_pct?: string | null;
    iterations: number;
    seed: number;
  };
  explain: Explain;
}

/** GET/POST /api/plan/{ws}/saved */
export interface SavedScenario {
  id: string;
  ws_id: string;
  scenario_id: string;
  name: string;
  inputs: ScenarioInputs;
  created_at: string;
  updated_at?: string | null;
}

/* ----------------------------------------------------------------- research */

/** A citation's cross-references (research graph layer). */
export interface RelatedRef {
  law: string;
  article: string;
}

/** GET /api/research/refs?law=&article= */
export interface RefsGraph {
  law: string;
  article: string;
  cites: RelatedRef[];
  cited_by: RelatedRef[];
}

/* -------------------------------------------------------------------- watch */

/** GET /api/watch/sources */
export interface WatchSource {
  id: string;
  name: string;
  jurisdiction: string;
  doc_type: string;
  fetch_method: string;
  cadence: string;
  trust_tier: TrustTier;
  url: string;
  domains?: string[];
}

export interface WatchSnapshot {
  source_id: string;
  fetched_at: string;
  content_hash: string;
  bytes: number;
}

/** GET /api/watch/sources/{id}/history */
export interface WatchSourceHistory {
  source_id: string;
  snapshots: WatchSnapshot[];
  changes: LawChange[];
}

/** GET /api/watch/proposals — the flat row shape the live API returns. */
export interface WatchProposal {
  id: string;
  change_id: string;
  rule_id: string;
  field: string;
  old_value: string;
  new_value: string;
  status: string;
  created_at: string;
}

/* Business, insights, reports and workflows wire types live in ./types-business. */
export * from "./types-business";
