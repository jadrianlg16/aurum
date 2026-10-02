/**
 * "Mi dinero" money organizer.
 *
 * Shapes are verified against the real API responses captured in `docs/api-samples.json`
 * (`GET/POST /organizer/demo-mx/...`) and cross-checked against `docs/modules/organizer.md`.
 * List endpoints are bare arrays, and every optional field is declared optional so a backend
 * that omits it never crashes a screen. See `docs/modules/web-ui.md` for the verification
 * notes and anything still unconfirmed (`POST /setup/run`, `paydays`).
 *
 * Money is a `str(Decimal)` inside `Amount` — never a number, never arithmetic here. Note
 * that `pct` (plan items) and `savings_rate` (plan) are ALSO serialized decimal strings, not
 * numbers — convert with `Number(...)` only for chart/progress-bar geometry, never to display.
 */
import type { Amount, Explain } from './types';

export type CommitmentKind =
  | 'subscription'
  | 'bill'
  | 'utility'
  | 'rent'
  | 'insurance'
  | 'loan_payment'
  | 'tax'
  | 'income'
  | 'transfer'
  | 'other';

export const COMMITMENT_KINDS: readonly CommitmentKind[] = [
  'subscription',
  'bill',
  'utility',
  'rent',
  'insurance',
  'loan_payment',
  'tax',
  'income',
  'transfer',
  'other',
];

export type Cadence =
  | 'weekly'
  | 'biweekly'
  | 'monthly'
  | 'bimonthly'
  | 'quarterly'
  | 'semiannual'
  | 'annual'
  | 'custom';

export const CADENCES: readonly Cadence[] = [
  'weekly',
  'biweekly',
  'monthly',
  'bimonthly',
  'quarterly',
  'semiannual',
  'annual',
  'custom',
];

export type Essential = 'needs' | 'wants' | 'savings' | 'debt';
export const ESSENTIALS: readonly Essential[] = ['needs', 'wants', 'savings', 'debt'];

export type CommitmentStatus = 'active' | 'paused' | 'cancelled' | 'trial';
export const COMMITMENT_STATUSES: readonly CommitmentStatus[] = ['active', 'paused', 'cancelled', 'trial'];

export type CommitmentSource = 'detected' | 'manual' | 'imported';

export interface Commitment {
  id: string;
  ws_id: string;
  kind: CommitmentKind;
  name: string;
  merchant_patterns: string[];
  amount: Amount;
  amount_variable: boolean;
  cadence: Cadence;
  interval_days?: number | null;
  anchor_day?: number | null;
  weekday?: number | null;
  next_due: string;
  account: string;
  /** The pf account (resolved server-side to `account`). */
  account_id?: string | null;
  account_name?: string | null;
  label_id?: string | null;
  essential: Essential;
  status: CommitmentStatus;
  trial_ends?: string | null;
  started?: string | null;
  ended?: string | null;
  auto_pay: boolean;
  cancel_notes?: string | null;
  linked_loan_id?: string | null;
  linked_card_id?: string | null;
  source: CommitmentSource;
  confidence: number;
  last_seen?: string | null;
  notes?: string | null;
  category_hint?: string | null;
  reviewed_at?: string | null;
  explain?: Explain | null;
  /** `amount × periods_per_year / 12` — present on every list/detail response. */
  monthly_equivalent?: Amount | null;
  annual_equivalent?: Amount | null;
}

/**
 * A commitment shown before it is persisted: `POST /quickadd`'s `preview` (no `?save=1` yet)
 * omits `id`/`ws_id`/`reviewed_at` entirely, while `POST /detect`'s candidate `preview` carries
 * `id: ""` and a real `ws_id`. Both parse against this relaxed shape.
 */
export type CommitmentPreview = Omit<Commitment, 'id' | 'ws_id' | 'reviewed_at'> &
  Partial<Pick<Commitment, 'id' | 'ws_id' | 'reviewed_at'>>;

/** The write body of POST/PUT /commitments — the server fills ids, explain and confidence. */
export interface CommitmentInput {
  kind: CommitmentKind;
  name: string;
  merchant_patterns?: string[];
  amount: Amount;
  amount_variable?: boolean;
  cadence: Cadence;
  interval_days?: number | null;
  anchor_day?: number | null;
  weekday?: number | null;
  next_due: string;
  /** Advanced only — personal forms send `account_id`. */
  account?: string;
  account_id?: string | null;
  label_id?: string | null;
  essential: Essential;
  status?: CommitmentStatus;
  trial_ends?: string | null;
  auto_pay?: boolean;
  notes?: string | null;
  /** Skip the duplicate-name 409. */
  force?: boolean;
}

/** PUT /commitments/{id} is a PATCH-merge: every field optional, unset stays untouched. */
export type CommitmentPatch = Partial<CommitmentInput>;

/** POST /organizer/{ws}/occurrences/mark (body, verbatim). */
export interface MarkOccurrenceBody {
  commitment_id: string;
  date: string;
  status: 'paid' | 'skipped';
  entry_id?: string | null;
  /** Create the pf entry when no matching one exists (stamped with `commitment_id`). */
  log_entry?: boolean;
  amount?: Amount | null;
  account_id?: string | null;
}

export interface MarkedOccurrence {
  commitment_id: string;
  due: string;
  status: OccurrenceStatus;
  txn_id?: string | null;
  amount?: Amount | null;
  entry_id?: string | null;
  auto_created: boolean;
}

export interface MarkOccurrenceResult {
  occurrence: MarkedOccurrence;
  entry_id: string | null;
  /** Legacy alias servers still send. */
  ok?: boolean;
}

/** DELETE /occurrences/mark → un-marked; the auto-created, unedited entry is voided. */
export interface UnmarkOccurrenceResult {
  removed: boolean;
  voided_entry_id: string | null;
}

export type OccurrenceStatus = 'upcoming' | 'due' | 'paid' | 'missed' | 'skipped';

export interface Occurrence {
  commitment_id: string;
  due: string;
  amount: Amount;
  status: OccurrenceStatus;
  /** False → one-tap 'Pagado'; true or absent → log the movement first (Registrar). */
  amount_variable?: boolean;
  txn_id?: string | null;
  /** `/summary.next_7_days` carries the commitment name alongside the occurrence. */
  name?: string | null;
  kind?: CommitmentKind | null;
}

export interface PricePoint {
  date: string;
  amount: Amount;
  source?: CommitmentSource | null;
}

export interface LoanProgress {
  loan_id: string;
  name?: string | null;
  payments_made?: number | null;
  payments_total?: number | null;
  months_left?: number | null;
  paid?: Amount | null;
  remaining?: Amount | null;
  principal?: Amount | null;
  payment?: Amount | null;
}

/** GET /commitments/{id} — the row plus its history, occurrences and loan link. */
export interface CommitmentDetail extends Commitment {
  price_history?: PricePoint[];
  occurrences?: Occurrence[];
  loan?: LoanProgress | null;
}

export type AlertKind =
  | 'price_increase'
  | 'price_decrease'
  | 'trial_ending'
  | 'missed_payment'
  | 'upcoming'
  | 'duplicate'
  | 'annual_renewal'
  | 'forgotten'
  // organizer/alerts.py also emits these
  | 'income_expected'
  | 'income_late'
  | 'income_changed'
  | 'cancelled_still_charging';

export type AlertSeverity = 'urgent' | 'warn' | 'info';

export interface OrgAlert {
  id: string;
  kind: AlertKind;
  severity: AlertSeverity;
  commitment_id?: string | null;
  title: string;
  body?: string | null;
  old_amount?: Amount | null;
  new_amount?: Amount | null;
  due?: string | null;
  explain?: Explain | null;
}

/** The one 'Disponible'. `parts` and `currency` are optional for older servers; explain step ids are fixed. */
export interface SafeToSpendParts {
  balance: Amount;
  fixed_pending: Amount;
  budgets_remaining: Amount;
  buffer: Amount;
}

export interface SafeToSpend {
  amount: Amount;
  until: string;
  currency?: string;
  parts?: SafeToSpendParts;
  explain?: Explain | null;
}

/** The explain step ids of `safe_to_spend`, in order. */
export const SAFE_TO_SPEND_STEPS = [
  'liquid_balance',
  'until',
  'committed_until',
  'budgeted_remaining',
  'buffer',
  'safe_to_spend',
] as const;

export interface SetupCounts {
  bank_lines: number;
  commitments: number;
  income_commitments: number;
  budgets: number;
  open_candidates: number;
}

/** `GET /setup/status` (and the `summary.setup` embed) — confirmed against api-samples.json. */
export interface SetupStatus {
  has_bank_lines: boolean;
  has_commitments: boolean;
  has_income: boolean;
  has_plan: boolean;
  counts?: SetupCounts | null;
  /** e.g. `"4/4"`. */
  progress?: string | null;
  explain?: Explain | null;
}

export interface OrganizerSummary {
  monthly_committed: { total: Amount; by_kind: Record<string, Amount> };
  annual_subscriptions: Amount;
  next_7_days: Occurrence[];
  alerts_count: number;
  safe_to_spend: SafeToSpend;
  uncategorized_count: number;
  setup: SetupStatus;
  explain?: Explain | null;
}

/** `POST /quickadd` — the body key is `preview`, never `commitment`; `save=1` persists it. */
export interface QuickAddPreview {
  preview: CommitmentPreview;
  saved: boolean;
  auto_label?: string | null;
  explain?: Explain | null;
}

export interface DetectEvidence {
  date: string;
  amount: Amount;
  description: string;
  source?: 'bank' | 'ledger' | 'cfdi' | string;
}

export type CandidateStatus = 'open' | 'accepted' | 'dismissed';

/** One row of `POST/GET /detect` — the parsed proposal is `preview`, never `commitment`. */
export interface Candidate {
  id: string;
  merchant: string;
  preview: CommitmentPreview;
  evidence: DetectEvidence[];
  confidence: number;
  status?: CandidateStatus;
}

/** Not yet checked against a live sample — `POST /setup/run`'s payday shape is a best guess. */
export interface Payday {
  date: string;
  amount: Amount;
  cadence?: Cadence | null;
}

/** `POST /detect` and `GET /detect` (the resumable, persisted list) share this shape. */
export interface DetectResult {
  candidates: Candidate[];
  count?: number;
  explain?: Explain | null;
}

export type CalendarItemKind = 'commitment' | 'card_cut' | 'card_due' | 'loan' | 'tax' | 'income';

export interface CalendarItem {
  kind: CalendarItemKind;
  /** The calendar day this item falls on — the field is `date`, not `due`. */
  date: string;
  id: string;
  name: string;
  amount: Amount;
  status: OccurrenceStatus;
  txn_id?: string | null;
  commitment_kind?: CommitmentKind | null;
  /** The pf account behind the item and the entry it was matched/created as. */
  account_id?: string | null;
  account_name?: string | null;
  entry_id?: string | null;
  /** False → one-tap 'Pagado'; true or absent → log the movement first (Registrar). */
  amount_variable?: boolean;
}

export interface CalendarDay {
  date: string;
  items: CalendarItem[];
  total_out: Amount;
  total_in: Amount;
}

export interface OrganizerCalendar {
  days: CalendarDay[];
  explain?: Explain | null;
}

export interface ForecastPoint {
  date: string;
  balance: Amount;
  in: Amount;
  out: Amount;
}

export interface Forecast {
  start_balance: Amount;
  series: ForecastPoint[];
  low_point: { date: string; balance: Amount };
  safe_to_spend: SafeToSpend;
  buffer?: Amount | null;
  explain?: Explain | null;
}

export interface PlanItem {
  label_id?: string | null;
  commitment_id?: string | null;
  name: string;
  account?: string | null;
  planned: Amount;
  actual: Amount;
  left: Amount;
  /** A serialized `Decimal` string (e.g. `"0.6082"`), like every other number here — not a float. */
  pct: string;
}

export interface PlanGroup {
  group: Essential;
  planned: Amount;
  actual: Amount;
  left: Amount;
  items: PlanItem[];
}

export interface UncategorizedTxn {
  txn_id: string;
  date: string;
  payee: string;
  amount: Amount;
}

export interface OrganizerPlan {
  period: string;
  groups: PlanGroup[];
  income_expected: Amount;
  income_actual: Amount;
  /** A serialized `Decimal` string (e.g. `"0.4378"`) — not a float. */
  savings_rate: string;
  uncategorized: UncategorizedTxn[];
  explain?: Explain | null;
}

export interface OrganizeAssignment {
  txn_id: string;
  label_id: string;
  create_rule?: boolean;
}

export interface OrganizeResult {
  assigned: number;
  rules_created?: number;
  explain?: Explain | null;
}

export interface OrganizerRule {
  id: string;
  pattern: string;
  label_id: string;
  label_name?: string | null;
  created_at?: string | null;
}

export interface SetupRunResult {
  status: SetupStatus;
  detected: number;
  planned?: number | null;
  candidates: Candidate[];
  paydays?: Payday[];
  plan?: { groups: { group: Essential; planned: Amount }[]; income_expected?: Amount | null } | null;
  explain?: Explain | null;
}

export interface OkResult {
  ok: boolean;
}
