/**
 * The personal, manual-first shapes.
 *
 * These are the only shapes in the app that a *person* is expected to think in: an account
 * with a friendly name, a movement with an amount and a category, an income stream with
 * paydays. No postings, no Beancount account strings — the ledger stays underneath.
 *
 * Everything an older backend might not send is optional and guarded at every read site, so
 * the UI degrades to "not set up yet" rather than crashing on a missing field.
 */
import type { Amount } from './types';

/* ------------------------------------------------------------------ accounts */

export type PfAccountType =
  | 'checking'
  | 'savings'
  | 'cash'
  | 'credit_card'
  | 'loan'
  | 'investment'
  | 'other';

export const PF_ACCOUNT_TYPES: PfAccountType[] = [
  'checking',
  'savings',
  'cash',
  'credit_card',
  'loan',
  'investment',
  'other',
];

/** A row of `GET /api/pf/{ws}/accounts` → `accounts[]`. */
export interface PfAccount {
  id: string;
  name: string;
  type: PfAccountType;
  institution?: string | null;
  currency?: string | null;
  /** The derived ledger account (= `ledger_account`). Advanced mode only, never in a personal form. */
  account?: string | null;
  ledger_account?: string | null;
  /** Assets → balance; credit_card|loan → what is OWED, positive. */
  balance?: Amount | null;
  /** The ledger-signed balance (liabilities negative). */
  balance_signed?: Amount | null;
  /** True for credit_card|loan rows — `balance` reads "you owe". */
  owed?: boolean;
  opening_balance?: Amount | null;
  opening_date?: string | null;
  credit_limit?: Amount | null;
  cut_day?: number | null;
  due_day?: number | null;
  /** Fraction string ("0.14") — kept for compat; the UI shows `apr_percent`. */
  apr?: string | null;
  /** Percent string ("14"). */
  apr_percent?: string | null;
  loan_months?: number | null;
  loan_principal?: Amount | null;
  archived?: boolean | null;
}

/** `POST /accounts` / `PUT /accounts/{id}`. */
export interface PfAccountInput {
  name: string;
  type: PfAccountType;
  institution?: string | null;
  currency?: string;
  opening_balance?: Amount | null;
  opening_date?: string | null;
  credit_limit?: Amount | null;
  cut_day?: number | null;
  due_day?: number | null;
  /** @deprecated fraction; send `apr_percent`. */
  apr?: string | null;
  apr_percent?: string | null;
  loan_months?: number | null;
  loan_principal?: Amount | null;
  archived?: boolean;
}

/** `POST /accounts/{id}/adjust`. */
export interface PfAccountAdjust {
  balance: Amount;
  date: string;
  note?: string | null;
}

/* ------------------------------------------------------------------- entries */

export type EntryKind = 'expense' | 'income' | 'transfer';

export const ENTRY_KINDS: EntryKind[] = ['expense', 'income', 'transfer'];

export type EntrySource =
  | 'manual'
  | 'quickadd'
  | 'import'
  | 'cfdi'
  | 'payroll'
  | 'organizer';

export interface EntrySplit {
  label_id: string;
  amount: Amount;
  note?: string | null;
}

/** A row of `GET /api/pf/{ws}/entries` — a movement, never a posting. */
export interface Entry {
  id: string;
  date: string;
  kind: EntryKind;
  /** Positive for income, negative for expense. */
  amount: Amount;
  account_id?: string | null;
  account_name?: string | null;
  to_account_id?: string | null;
  to_account_name?: string | null;
  label_id?: string | null;
  label_name?: string | null;
  payee?: string | null;
  note?: string | null;
  tags?: string[] | null;
  splits?: EntrySplit[] | null;
  source?: EntrySource | null;
  attachment?: string | null;
  txn_id?: string | null;
  /** False when rewriting the ledger row would move a tax figure. */
  editable?: boolean | null;
  /** Why `editable` is false (a code such as `source:cfdi`), else null. */
  non_editable_reason?: string | null;
  /** The fixed payment this entry was logged for. */
  commitment_id?: string | null;
  /** Voided rows never come back in lists; only a stale detail can carry `true`. */
  voided?: boolean;
}

/** GET /pf/{ws}/entries: totals over the FULL filtered set; the UI never sums itself. */
export interface EntriesPage {
  entries: Entry[];
  /** Opaque keyset token (`date|id` of the last row); null on the last page. */
  next_cursor: string | null;
  totals: { in: Amount; out: Amount; net: Amount; count: number };
}

/** DELETE /entries/{id}. */
export interface EntryVoidResult {
  id: string;
  voided: true;
}

/** POST /entries/bulk — all-or-nothing. */
export interface BulkCreateResult {
  created: string[];
}

/** `POST /entries` / `PUT /entries/{id}` — what the Agregar dialog sends. */
export interface EntryInput {
  kind: EntryKind;
  date: string;
  amount: Amount;
  account_id: string;
  to_account_id?: string | null;
  label_id?: string | null;
  payee?: string | null;
  note?: string | null;
  tags?: string[] | null;
  splits?: { label_id: string; amount: Amount; note?: string | null }[] | null;
  /** Set when logging an occurrence from Mi dinero. */
  commitment_id?: string | null;
  /** Receipt photo id (`rcp-…`, POST /ingest/{ws}/receipts). */
  attachment?: string | null;
}

/* ---- Receipt photos (aurum/ingest/receipts.py) ---- */

export type ReceiptConfidence = 'high' | 'medium' | 'low' | null;

export interface ReceiptSuggestion {
  amount: Amount | null;
  date: string | null;
  payee: string | null;
  label_id: string | null;
  label_name: string | null;
  confidence: { amount: ReceiptConfidence; date: ReceiptConfidence; payee: ReceiptConfidence; label: ReceiptConfidence };
}

/** POST /api/ingest/{ws}/receipts and GET …/receipts/{id}. Nothing is saved as a movement. */
export interface ReceiptScan {
  receipt: { id: string; url: string; content_type: string; size: number; created_at: string };
  ocr: { engine: string | null; ok: boolean; error: string | null; chars: number; seconds?: number; text: string };
  suggestion: ReceiptSuggestion | null;
  /** Plain sentences, one per guess ("Monto: la línea «TOTAL 79.50»."). */
  reasons: string[];
  /** Set when OCR is off, failed or found no total: the photo is kept, the amount is typed. */
  message?: string | null;
  /** A movement this ticket may already be (same photo, or same date + amount + shop). A warning only. */
  duplicate?: { entry_id: string; date: string; amount: Amount; payee: string | null; same_photo: boolean } | null;
}

export interface EntryQuery {
  from?: string;
  to?: string;
  account_id?: string;
  label_id?: string;
  kind?: EntryKind | '';
  q?: string;
  /** Rows linked to one Mi dinero commitment (GET /entries?commitment_id=). */
  commitment_id?: string;
  /** Default 100, max 500 (the server answers 422 above). */
  limit?: number;
  cursor?: string;
}

/** POST /ingest/{ws}/quickadd: the parsed preview; `entry` is set after `commit`. */
export interface QuickAddResult {
  preview: {
    kind: EntryKind;
    amount: Amount;
    account_id: string | null;
    account_name: string | null;
    label_id: string | null;
    label_name: string | null;
    payee: string | null;
    date: string;
  };
  confidence: number;
  warnings: string[];
  entry: Entry | null;
  /** Keys an older server still sends (inbox item fields) are tolerated. */
  [extra: string]: unknown;
}

/** POST /ingest/{ws}/bank/csv. */
export interface BankCsvResult {
  created: string[];
  skipped_duplicates: number;
  errors: { line: number; detail: string }[];
}

/* ------------------------------------------------------------ income streams */

export type StreamSourceType =
  | 'salary'
  | 'freelance'
  | 'rent'
  | 'pension'
  | 'investment'
  | 'other';

export const STREAM_SOURCE_TYPES: StreamSourceType[] = [
  'salary',
  'freelance',
  'rent',
  'pension',
  'investment',
  'other',
];

export type StreamCadence =
  | 'monthly'
  | 'semimonthly'
  | 'biweekly'
  | 'weekly'
  | 'annual'
  | 'irregular';

export const STREAM_CADENCES: StreamCadence[] = [
  'monthly',
  'semimonthly',
  'biweekly',
  'weekly',
  'annual',
  'irregular',
];

export interface IncomeStream {
  id: string;
  name: string;
  /** The organizer income commitments mirrored from this stream (aurum/pf/streams.py). */
  commitment_ids?: string[] | null;
  source_type: StreamSourceType;
  amount: Amount;
  gross_amount?: Amount | null;
  cadence: StreamCadence;
  /** Days of the month a payment lands; `31` means "last day". */
  anchor_days?: number[] | null;
  weekday?: number | null;
  next_expected?: string | null;
  account_id?: string | null;
  account_name?: string | null;
  label_id?: string | null;
  active?: boolean | null;
  notes?: string | null;
}

export interface IncomeStreamInput {
  name: string;
  source_type: StreamSourceType;
  amount: Amount;
  gross_amount?: Amount | null;
  cadence: StreamCadence;
  anchor_days?: number[] | null;
  weekday?: number | null;
  next_expected?: string | null;
  account_id?: string | null;
  label_id?: string | null;
  active?: boolean;
  notes?: string | null;
}

/**
 * One occurrence of GET /income/streams/{id}/history — the REAL backend row
 * (aurum/pf/streams.py): a due date, what was expected, what landed, and a status.
 */
export interface StreamHistoryRow {
  due: string;
  expected: Amount | null;
  received: Amount | null;
  status: 'received' | 'late' | 'pending' | 'missed' | string;
  /**
   * @deprecated an older mock invented a per-period row; the server sends `due`. The client
   * wrapper (`getStreamHistory`) derives it as `due.slice(0, 7)` so IncomeStreams keeps typing.
   */
  period: string;
  /** @deprecated older mock field. */
  count?: number | null;
}

export interface StreamHistory {
  stream_id?: string;
  periods: StreamHistoryRow[];
}

/* --------------------------------------------------------------- onboarding */

/** The four real steps. `done` = accounts.done && first_entries.done. */
export type OnboardingStepKey = 'accounts' | 'income' | 'recurring' | 'first_entries';

/**
 * @deprecated older step union, kept unchanged; use `OnboardingStepKey`.
 */
export type OnboardingStepId = 'accounts' | 'income' | 'recurring' | 'categories' | 'import';

export interface OnboardingStep {
  id: OnboardingStepKey;
  done: boolean;
  count?: number | null;
  hint?: string | null;
}

export interface Onboarding {
  steps: OnboardingStep[];
  done: boolean;
}

/** @deprecated use `Onboarding`. */
export type OnboardingStatus = Onboarding;

/* ------------------------------------------------------------ simple/advanced */

export type UiMode = 'simple' | 'advanced';

export type ModuleKey =
  | 'tax'
  | 'business'
  | 'research'
  | 'watch'
  | 'workflows'
  | 'reports'
  | 'crossborder'
  | 'holdings';

export const MODULE_KEYS: ModuleKey[] = [
  'tax',
  'business',
  'research',
  'watch',
  'workflows',
  'reports',
  'crossborder',
  'holdings',
];

export type Modules = Partial<Record<ModuleKey, boolean>>;
