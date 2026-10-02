/**
 * Mock fixtures + in-memory behaviour for the "Mi dinero" organizer.
 *
 * Unlike the earlier fixture files this one is *live*: the whole organizer is a tiny
 * in-memory implementation, because the hub only makes sense when things actually change —
 * marking a charge paid moves a dot on the calendar, accepting a candidate creates a
 * commitment, auto-planning fills the plan, and bulk-labelling empties the uncategorized
 * list. `index.ts` only routes; every rule lives here.
 *
 * Money discipline: every amount is produced as a decimal *string*. Sums are done in integer
 * centavos with BigInt (the mock's stand-in for the API's Decimal) — no binary float ever
 * produces a figure the UI displays.
 *
 * Dates are relative to "today" so the demo is always alive: the trial ends in 5 days, one
 * gym charge was missed, and the forecast starts now.
 */
import type { Amount, Explain } from '../types';
import {
  PF5,
  detailError,
  pfCreateEntry,
  pfDeleteEntry,
  pfEntryUntouched,
  pfFindMatchingEntry,
  pfGetAccount,
} from './fixtures-personal';
import type { MarkOccurrenceBody, MarkOccurrenceResult, SafeToSpendParts, UnmarkOccurrenceResult } from '../types-organizer';
import type {
  Cadence,
  Candidate,
  Commitment,
  CommitmentDetail,
  CommitmentInput,
  CommitmentKind,
  CommitmentStatus,
  DetectResult,
  Forecast,
  ForecastPoint,
  Occurrence,
  OccurrenceStatus,
  OrgAlert,
  OrganizeAssignment,
  OrganizeResult,
  OrganizerCalendar,
  OrganizerPlan,
  OrganizerRule,
  OrganizerSummary,
  Payday,
  PlanGroup,
  PlanItem,
  PricePoint,
  QuickAddPreview,
  SetupRunResult,
  SetupStatus,
  UncategorizedTxn,
  Essential,
} from '../types-organizer';

/** `amount × periods_per_year / 12` — normalizes any cadence to a monthly figure. */
const PERIODS_PER_YEAR: Partial<Record<Cadence, number>> = {
  weekly: 52,
  biweekly: 26,
  monthly: 12,
  bimonthly: 6,
  quarterly: 4,
  semiannual: 2,
  annual: 1,
};

function withEquivalents(c: Commitment): Commitment {
  const periods = PERIODS_PER_YEAR[c.cadence] ?? 12;
  const monthly = fromCents((toCents(c.amount.amount) * BigInt(periods)) / 12n);
  const annual = fromCents(toCents(c.amount.amount) * BigInt(periods));
  return { ...c, monthly_equivalent: amt(monthly, c.amount.currency), annual_equivalent: amt(annual, c.amount.currency) };
}

const WS_ID = 'demo-mx';
const MXN = 'MXN';

/* ------------------------------------------------------------- decimal ---- */

const toCents = (d: string): bigint => {
  const neg = d.trim().startsWith('-');
  const [int = '0', frac = ''] = d.trim().replace(/^[+-]/, '').split('.');
  const cents = BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2) || '0');
  return neg ? -cents : cents;
};

const fromCents = (c: bigint): string => {
  const neg = c < 0n;
  const abs = neg ? -c : c;
  const int = abs / 100n;
  const frac = (abs % 100n).toString().padStart(2, '0');
  return `${neg ? '-' : ''}${int}.${frac}`;
};

const amt = (amount: string, currency = MXN): Amount => ({ amount, currency });
const centsAmt = (c: bigint, currency = MXN): Amount => amt(fromCents(c), currency);
const sum = (values: string[]): string => fromCents(values.reduce((a, v) => a + toCents(v), 0n));
const mul = (value: string, times: number): string => fromCents(toCents(value) * BigInt(times));

const explain = (
  summary: string,
  steps: { id?: string; label: string; formula?: string | null; value: string }[] = [],
): Explain => ({
  summary,
  steps: steps.map((s) => ({ ...(s.id ? { id: s.id } : {}), label: s.label, formula: s.formula ?? null, value: s.value })),
  citations: [],
  rule_versions: [],
  confidence: null,
});

/* ---------------------------------------------------------------- dates ---- */

const D = 86_400_000;
const startOfToday = (): Date => {
  const n = new Date();
  return new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()));
};
const TODAY = startOfToday();
const iso = (d: Date): string => d.toISOString().slice(0, 10);
const addDays = (d: Date, n: number): Date => new Date(d.getTime() + n * D);
const parse = (s: string): Date => new Date(`${s.slice(0, 10)}T00:00:00Z`);
const TODAY_ISO = iso(TODAY);

/** The nth-of-the-month date in the month `monthOffset` months from today, clamped. */
function dayOfMonth(day: number, monthOffset = 0): string {
  const y = TODAY.getUTCFullYear();
  const m = TODAY.getUTCMonth() + monthOffset;
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return iso(new Date(Date.UTC(y, m, Math.min(day, last))));
}

/** The next occurrence of day-of-month `day` that is today or later. */
function nextDayOfMonth(day: number): string {
  const thisMonth = dayOfMonth(day, 0);
  return thisMonth >= TODAY_ISO ? thisMonth : dayOfMonth(day, 1);
}

const CADENCE_MONTHS: Partial<Record<Cadence, number>> = {
  monthly: 1,
  bimonthly: 2,
  quarterly: 3,
  semiannual: 6,
  annual: 12,
};

/** Step one cadence forward from an ISO date. Dates only — no money involved. */
function advance(date: string, c: Commitment): string {
  const d = parse(date);
  if (c.cadence === 'weekly') return iso(addDays(d, 7));
  if (c.cadence === 'biweekly') return iso(addDays(d, 14));
  if (c.cadence === 'custom') return iso(addDays(d, c.interval_days ?? 30));
  const months = CADENCE_MONTHS[c.cadence] ?? 1;
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() + months;
  const day = c.anchor_day ?? d.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return iso(new Date(Date.UTC(y, m, Math.min(day, last))));
}

/** Step one cadence backwards (used to walk price history / past occurrences). */
function retreat(date: string, c: Commitment): string {
  const d = parse(date);
  if (c.cadence === 'weekly') return iso(addDays(d, -7));
  if (c.cadence === 'biweekly') return iso(addDays(d, -14));
  if (c.cadence === 'custom') return iso(addDays(d, -(c.interval_days ?? 30)));
  const months = CADENCE_MONTHS[c.cadence] ?? 1;
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() - months;
  const day = c.anchor_day ?? d.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return iso(new Date(Date.UTC(y, m, Math.min(day, last))));
}

/* ----------------------------------------------------------------- seed ---- */

let seq = 0;
const nid = (p: string) => `${p}-${(seq += 1)}`;

interface Seed {
  id: string;
  kind: CommitmentKind;
  name: string;
  patterns: string[];
  amount: string;
  cadence: Cadence;
  day: number;
  account: string;
  essential: Essential;
  status?: CommitmentStatus;
  label_id?: string | null;
  variable?: boolean;
  hint?: string;
  monthsAhead?: number;
  trialDays?: number;
  loan?: string;
  notes?: string;
  source?: Commitment['source'];
  confidence?: number;
}

const SEEDS: Seed[] = [
  {
    id: 'cmt-netflix',
    kind: 'subscription',
    name: 'Netflix',
    patterns: ['NETFLIX', 'NETFLIX.COM'],
    amount: '219.00',
    cadence: 'monthly',
    day: 15,
    account: 'Liabilities:CreditCard:BBVA',
    essential: 'wants',
    hint: 'streaming',
    confidence: 0.97,
  },
  {
    id: 'cmt-max',
    kind: 'subscription',
    name: 'Max (prueba)',
    patterns: ['HBO MAX', 'MAX.COM'],
    amount: '149.00',
    cadence: 'monthly',
    day: 27,
    account: 'Liabilities:CreditCard:BBVA',
    essential: 'wants',
    status: 'trial',
    hint: 'streaming',
    trialDays: 5,
    source: 'manual',
    confidence: 1,
  },
  {
    id: 'cmt-spotify',
    kind: 'subscription',
    name: 'Spotify',
    patterns: ['SPOTIFY', 'SPOTIFY MX'],
    amount: '129.00',
    cadence: 'monthly',
    day: 8,
    account: 'Liabilities:CreditCard:BBVA',
    essential: 'wants',
    hint: 'music',
    confidence: 0.96,
  },
  {
    id: 'cmt-icloud',
    kind: 'subscription',
    name: 'iCloud+',
    patterns: ['APPLE.COM/BILL', 'ICLOUD'],
    amount: '49.00',
    cadence: 'monthly',
    day: 22,
    account: 'Liabilities:CreditCard:BBVA',
    essential: 'wants',
    hint: 'cloud',
    confidence: 0.93,
  },
  {
    id: 'cmt-gym',
    kind: 'subscription',
    name: 'Smart Fit',
    patterns: ['SMART FIT', 'SMARTFIT CENTRO'],
    amount: '649.00',
    cadence: 'monthly',
    day: 3,
    account: 'Assets:Bank:BBVA',
    essential: 'wants',
    hint: 'gym',
    confidence: 0.9,
  },
  {
    id: 'cmt-prime',
    kind: 'subscription',
    name: 'Amazon Prime (anual)',
    patterns: ['AMAZON PRIME', 'AMZN PRIME MX'],
    amount: '899.00',
    cadence: 'annual',
    day: 18,
    account: 'Liabilities:CreditCard:BBVA',
    essential: 'wants',
    hint: 'shopping',
    monthsAhead: 0,
    confidence: 0.88,
  },
  {
    id: 'cmt-telcel',
    kind: 'bill',
    name: 'Telcel',
    patterns: ['TELCEL', 'TELCEL PLAN'],
    amount: '399.00',
    cadence: 'monthly',
    day: 20,
    account: 'Assets:Bank:BBVA',
    essential: 'needs',
    hint: 'phone',
    confidence: 0.95,
  },
  {
    id: 'cmt-cfe',
    kind: 'utility',
    name: 'CFE',
    patterns: ['CFE SUMINISTRADOR', 'CFE'],
    amount: '1120.00',
    cadence: 'bimonthly',
    day: 12,
    account: 'Assets:Bank:BBVA',
    essential: 'needs',
    variable: true,
    hint: 'power',
    confidence: 0.84,
  },
  {
    id: 'cmt-renta',
    kind: 'rent',
    name: 'Renta',
    patterns: ['TRASPASO RENTA', 'SPEI RENTA'],
    amount: '12000.00',
    cadence: 'monthly',
    day: 1,
    account: 'Assets:Bank:BBVA',
    essential: 'needs',
    label_id: 'lbl-d92e338efc65',
    confidence: 1,
    source: 'manual',
  },
  {
    id: 'cmt-auto',
    kind: 'loan_payment',
    name: 'Crédito auto',
    patterns: ['PAGO CREDITO AUTO'],
    amount: '5000.00',
    cadence: 'monthly',
    day: 15,
    account: 'Assets:Bank:BBVA',
    essential: 'debt',
    loan: 'loan-b0529662e3e1',
    confidence: 1,
    source: 'manual',
  },
  {
    id: 'cmt-nomina-5',
    kind: 'income',
    name: 'Nómina (día 5)',
    patterns: ['NOMINA', 'DEPOSITO NOMINA'],
    amount: '25000.00',
    cadence: 'monthly',
    day: 5,
    account: 'Assets:Bank:BBVA',
    essential: 'needs',
    confidence: 0.99,
  },
  {
    id: 'cmt-nomina-20',
    kind: 'income',
    name: 'Nómina (día 20)',
    patterns: ['NOMINA', 'DEPOSITO NOMINA'],
    amount: '25000.00',
    cadence: 'monthly',
    day: 20,
    account: 'Assets:Bank:BBVA',
    essential: 'needs',
    confidence: 0.99,
  },
];

/**
 * Commitments carry the pf account (`account_id`/`account_name`); the ledger string is
 * derived from it. Seeds still name a ledger account, so resolve by ledger name first, then by
 * type (cards → the first card, everything else → the first checking/cash account).
 */
function resolvePfAccount(ledger: string | undefined, accountId?: string | null) {
  if (accountId) {
    const a = pfGetAccount(accountId);
    if (!a) throw detailError(404, `account ${accountId} not found`);
    return a;
  }
  const byLedger = ledger ? PF5.accounts.find((a) => a.ledger_account === ledger) : undefined;
  if (byLedger) return byLedger;
  if (ledger?.startsWith('Liabilities:CreditCard')) {
    return PF5.accounts.find((a) => a.type === 'credit_card') ?? PF5.accounts[0];
  }
  return PF5.accounts.find((a) => a.type === 'checking' || a.type === 'cash') ?? PF5.accounts[0];
}

function withAccount<T extends { account?: string; account_id?: string | null }>(c: T): T {
  const a = resolvePfAccount(c.account, c.account_id);
  return { ...c, account: a?.ledger_account ?? c.account ?? '', account_id: a?.id ?? null, account_name: a?.name ?? null };
}

function seedToCommitment(s: Seed): Commitment {
  const base: Commitment = {
    id: s.id,
    ws_id: WS_ID,
    kind: s.kind,
    name: s.name,
    merchant_patterns: s.patterns,
    amount: amt(s.amount),
    amount_variable: Boolean(s.variable),
    cadence: s.cadence,
    interval_days: null,
    anchor_day: s.day,
    weekday: null,
    next_due: nextDayOfMonth(s.day),
    account: s.account,
    label_id: s.label_id ?? null,
    essential: s.essential,
    status: s.status ?? 'active',
    trial_ends: s.trialDays ? iso(addDays(TODAY, s.trialDays)) : null,
    started: dayOfMonth(s.day, -14),
    ended: null,
    auto_pay: s.kind !== 'rent',
    cancel_notes: null,
    linked_loan_id: s.loan ?? null,
    linked_card_id: s.account.startsWith('Liabilities:CreditCard') ? 'card-bbva-azul' : null,
    source: s.source ?? 'detected',
    confidence: s.confidence ?? 0.9,
    last_seen: retreat(nextDayOfMonth(s.day), {
      cadence: s.cadence,
      anchor_day: s.day,
      interval_days: null,
    } as Commitment),
    notes: s.notes ?? null,
    category_hint: s.hint ?? null,
    explain: explain(
      `Detectado por ${s.patterns[0]} con ${s.cadence === 'monthly' ? '3' : '2'} cargos consecutivos.`,
      [{ label: 'Importe observado', formula: null, value: s.amount }],
    ),
  };
  if (s.cadence === 'annual') {
    base.next_due = iso(addDays(TODAY, 41));
  }
  return withEquivalents(base);
}

/* --------------------------------------------------------------- state ----- */

interface MarkRecord {
  status: OccurrenceStatus;
  txn_id?: string | null;
  entry_id?: string | null;
  amount?: Amount | null;
  auto_created?: boolean;
}

interface OrgState {
  commitments: Commitment[];
  /** `${commitment_id}|${due}` → what the user (or the matcher) said about it. */
  marks: Record<string, MarkRecord>;
  dismissedAlerts: Set<string>;
  candidates: Candidate[];
  dismissedCandidates: Set<string>;
  rules: OrganizerRule[];
  planned: Record<string, string>;
  uncategorized: UncategorizedTxn[];
  buffer: string;
  planSeeded: boolean;
  setupRan: boolean;
  /** Σ max(0, effective − spent) of this period's budgets — supplied by index.ts (it owns budgets). */
  budgetsRemaining: () => bigint;
}

const PRICE_HISTORY: Record<string, PricePoint[]> = {
  'cmt-netflix': [
    { date: dayOfMonth(15, -4), amount: amt('199.00') },
    { date: dayOfMonth(15, -3), amount: amt('199.00') },
    { date: dayOfMonth(15, -2), amount: amt('199.00') },
    { date: dayOfMonth(15, -1), amount: amt('219.00') },
  ],
  'cmt-cfe': [
    { date: dayOfMonth(12, -4), amount: amt('890.00') },
    { date: dayOfMonth(12, -2), amount: amt('1120.00') },
  ],
  'cmt-spotify': [
    { date: dayOfMonth(8, -3), amount: amt('129.00') },
    { date: dayOfMonth(8, -2), amount: amt('129.00') },
    { date: dayOfMonth(8, -1), amount: amt('129.00') },
  ],
};

const UNCATEGORIZED: UncategorizedTxn[] = [
  { txn_id: 'txn-u1', date: dayOfMonth(4, 0), payee: 'OXXO GAS SUR', amount: amt('-780.00') },
  { txn_id: 'txn-u2', date: dayOfMonth(7, 0), payee: 'MERCADO PAGO*VARIOS', amount: amt('-1240.50') },
  { txn_id: 'txn-u3', date: dayOfMonth(9, 0), payee: 'FARMACIA GUADALAJARA', amount: amt('-435.00') },
  { txn_id: 'txn-u4', date: dayOfMonth(11, 0), payee: 'UBER TRIP 3317', amount: amt('-189.00') },
  { txn_id: 'txn-u5', date: dayOfMonth(13, 0), payee: 'SUPERMERCADO DEMO', amount: amt('-2310.75') },
];

export const ORG: OrgState = {
  commitments: SEEDS.map(seedToCommitment),
  marks: {},
  dismissedAlerts: new Set<string>(),
  candidates: [],
  dismissedCandidates: new Set<string>(),
  rules: [
    { id: 'rul-1', pattern: 'OXXO GAS', label_id: 'lbl-6c72269a8eab', label_name: 'Súper', created_at: dayOfMonth(2, -1) },
  ],
  planned: {},
  uncategorized: UNCATEGORIZED.map((u) => ({ ...u })),
  buffer: '2000.00',
  planSeeded: false,
  setupRan: false,
  budgetsRemaining: () => 0n,
};
ORG.commitments = ORG.commitments.map(withAccount);

// One charge the user never paid: the gym, three days after it was due.
const GYM_MISSED_DUE = dayOfMonth(3, TODAY.getUTCDate() > 6 ? 0 : -1);
ORG.marks[`cmt-gym|${GYM_MISSED_DUE}`] = { status: 'missed' };

const byId = (id: string) => ORG.commitments.find((c) => c.id === id);

/* --------------------------------------------------- occurrence projection - */

/** Every due date of a commitment inside [from, to], walking its cadence. */
function duesBetween(c: Commitment, from: string, to: string): string[] {
  if (c.status === 'cancelled') return [];
  const out: string[] = [];
  // Walk back from `next_due` until before `from`, then forward to `to`.
  let cursor = c.next_due;
  let guard = 0;
  while (cursor > from && guard < 400) {
    cursor = retreat(cursor, c);
    guard += 1;
  }
  guard = 0;
  while (cursor <= to && guard < 400) {
    if (cursor >= from) out.push(cursor);
    cursor = advance(cursor, c);
    guard += 1;
  }
  return out;
}

function occurrenceStatus(c: Commitment, due: string): OccurrenceStatus {
  const mark = ORG.marks[`${c.id}|${due}`];
  if (mark) return mark.status;
  if (due < TODAY_ISO) return 'paid';
  if (due === TODAY_ISO) return 'due';
  return 'upcoming';
}

function occurrenceAmount(c: Commitment, due: string): Amount {
  const history = PRICE_HISTORY[c.id];
  if (history) {
    const past = history.filter((p) => p.date <= due);
    if (past.length > 0 && due < TODAY_ISO) return past[past.length - 1].amount;
  }
  return c.amount;
}

function occurrence(c: Commitment, due: string): Occurrence {
  const mark = ORG.marks[`${c.id}|${due}`];
  return {
    commitment_id: c.id,
    due,
    amount: occurrenceAmount(c, due),
    status: occurrenceStatus(c, due),
    txn_id: mark?.txn_id ?? (due < TODAY_ISO ? `txn-${c.id}-${due}` : null),
    name: c.name,
    kind: c.kind,
  };
}

const outflow = (c: Commitment) => c.kind !== 'income';
const active = (c: Commitment) => c.status === 'active' || c.status === 'trial';

/* ------------------------------------------------------------- summary ----- */

function monthRange(): { from: string; to: string } {
  const y = TODAY.getUTCFullYear();
  const m = TODAY.getUTCMonth();
  return { from: iso(new Date(Date.UTC(y, m, 1))), to: iso(new Date(Date.UTC(y, m + 1, 0))) };
}

export function orgSummary(): OrganizerSummary {
  const { from, to } = monthRange();
  const byKind: Record<string, bigint> = {};
  let total = 0n;
  for (const c of ORG.commitments) {
    if (!active(c) || !outflow(c) || c.status === 'trial') continue;
    for (const due of duesBetween(c, from, to)) {
      const cents = toCents(occurrenceAmount(c, due).amount);
      total += cents;
      byKind[c.kind] = (byKind[c.kind] ?? 0n) + cents;
    }
  }

  const subsMonthly = ORG.commitments
    .filter((c) => active(c) && c.kind === 'subscription' && c.cadence === 'monthly' && c.status !== 'trial')
    .map((c) => c.amount.amount);
  const subsAnnual = ORG.commitments
    .filter((c) => active(c) && c.kind === 'subscription' && c.cadence === 'annual')
    .map((c) => c.amount.amount);
  const annual = sum([mul(sum(subsMonthly), 12), ...subsAnnual]);

  const horizon = iso(addDays(TODAY, 7));
  const next7: Occurrence[] = [];
  for (const c of ORG.commitments) {
    if (!active(c)) continue;
    for (const due of duesBetween(c, TODAY_ISO, horizon)) next7.push(occurrence(c, due));
  }
  next7.sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : 0));

  const sts = orgSafeToSpend();

  return {
    monthly_committed: {
      total: centsAmt(total),
      by_kind: Object.fromEntries(Object.entries(byKind).map(([k, v]) => [k, centsAmt(v)])),
    },
    annual_subscriptions: amt(annual),
    next_7_days: next7,
    alerts_count: orgAlerts().length,
    safe_to_spend: sts,
    uncategorized_count: ORG.uncategorized.length,
    setup: orgSetupStatus(),
    explain: explain('Suma de los cargos proyectados del mes en curso, por tipo.', [
      { label: 'Cargos del mes', formula: `${from} → ${to}`, value: fromCents(total) },
      { label: 'Suscripciones al año', formula: 'mensuales × 12 + anuales', value: annual },
    ]),
  };
}

/* --------------------------------------------------------------- forecast -- */

const START_BALANCE = '127057.50'; // Assets:Bank:* + Assets:Cash, per the ledger fixtures.

function forecastSeries(days: number): ForecastPoint[] {
  const to = iso(addDays(TODAY, days));
  const inflow: Record<string, bigint> = {};
  const outflowByDay: Record<string, bigint> = {};
  for (const c of ORG.commitments) {
    if (!active(c)) continue;
    for (const due of duesBetween(c, TODAY_ISO, to)) {
      const cents = toCents(occurrenceAmount(c, due).amount);
      if (outflow(c)) outflowByDay[due] = (outflowByDay[due] ?? 0n) + cents;
      else inflow[due] = (inflow[due] ?? 0n) + cents;
    }
  }
  let balance = toCents(START_BALANCE);
  const series: ForecastPoint[] = [];
  for (let i = 0; i <= days; i += 1) {
    const date = iso(addDays(TODAY, i));
    const inC = inflow[date] ?? 0n;
    const outC = outflowByDay[date] ?? 0n;
    balance = balance + inC - outC;
    series.push({ date, balance: centsAmt(balance), in: centsAmt(inC), out: centsAmt(outC) });
  }
  return series;
}

/** Next income date at or after today — the day "safe to spend" runs until. */
function nextPayday(): string {
  const to = iso(addDays(TODAY, 60));
  const dates: string[] = [];
  for (const c of ORG.commitments) {
    if (!active(c) || outflow(c)) continue;
    dates.push(...duesBetween(c, iso(addDays(TODAY, 1)), to));
  }
  dates.sort();
  return dates[0] ?? iso(addDays(TODAY, 15));
}

/** The liquid balance: Σ non-archived cash/checking/savings pf accounts (signed). */
function liquidCents(): bigint {
  let total = 0n;
  for (const a of PF5.accounts) {
    if (a.archived) continue;
    if (a.type !== 'checking' && a.type !== 'savings' && a.type !== 'cash') continue;
    const bal = pfGetAccount(a.id)?.balance_signed?.amount ?? '0';
    total += toCents(bal);
  }
  return total;
}

/**
 * The one 'Disponible': balance − fixed_pending − budgets_remaining − buffer, with the
 * parts and explain step ids exactly as the API sends them.
 */
export function orgSafeToSpend(): OrganizerSummary['safe_to_spend'] {
  const until = nextPayday();
  let committed = 0n;
  for (const c of ORG.commitments) {
    if (!active(c) || !outflow(c)) continue;
    for (const due of duesBetween(c, iso(addDays(TODAY, -7)), until)) {
      const st = occurrenceStatus(c, due);
      if (st === 'paid' || st === 'skipped') continue;
      if (due < TODAY_ISO && st !== 'missed') continue;
      committed += toCents(occurrenceAmount(c, due).amount);
    }
  }
  const liquid = liquidCents();
  const budgets = ORG.budgetsRemaining();
  const buffer = toCents(ORG.buffer);
  const safe = liquid - committed - budgets - buffer;
  const parts: SafeToSpendParts = {
    balance: centsAmt(liquid),
    fixed_pending: centsAmt(committed),
    budgets_remaining: centsAmt(budgets),
    buffer: centsAmt(buffer),
  };
  return {
    amount: centsAmt(safe),
    until,
    currency: MXN,
    parts,
    explain: explain('Lo que tienes en cuentas líquidas, menos los pagos fijos pendientes hasta tu próximo ingreso, menos lo que falta por gastar de tus presupuestos, menos tu colchón.', [
      { id: 'liquid_balance', label: 'Saldo en cuentas', formula: 'efectivo y bancos', value: fromCents(liquid) },
      { id: 'until', label: 'Hasta', formula: 'tu próximo ingreso', value: until },
      { id: 'committed_until', label: 'Pagos fijos pendientes', formula: `de hoy al ${until}`, value: fromCents(committed) },
      { id: 'budgeted_remaining', label: 'Presupuesto restante', formula: 'lo que falta por gastar este mes', value: fromCents(budgets) },
      { id: 'buffer', label: 'Colchón', formula: 'lo que prefieres no tocar', value: ORG.buffer },
      { id: 'safe_to_spend', label: 'Disponible', formula: 'saldo − pagos fijos − presupuesto restante − colchón', value: fromCents(safe) },
    ]),
  };
}

export function orgForecast(days: number): Forecast {
  const series = forecastSeries(days);
  let low = series[0];
  for (const p of series) if (toCents(p.balance.amount) < toCents(low.balance.amount)) low = p;
  return {
    start_balance: amt(START_BALANCE),
    series,
    low_point: { date: low.date, balance: low.balance },
    safe_to_spend: orgSafeToSpend(),
    buffer: amt(ORG.buffer),
    explain: explain(`Saldo proyectado a ${days} días con los cargos e ingresos programados.`, [
      { label: 'Saldo inicial', formula: 'Assets:Bank:* + Assets:Cash', value: START_BALANCE },
      { label: 'Punto más bajo', formula: low.date, value: low.balance.amount },
    ]),
  };
}

/* ----------------------------------------------------------------- alerts -- */

export function orgAlerts(): OrgAlert[] {
  const out: OrgAlert[] = [];
  const push = (a: OrgAlert) => {
    if (!ORG.dismissedAlerts.has(a.id)) out.push(a);
  };

  for (const c of ORG.commitments) {
    if (!active(c)) continue;

    const history = PRICE_HISTORY[c.id];
    if (history && history.length >= 2) {
      const prev = history[history.length - 2].amount;
      const last = history[history.length - 1].amount;
      const delta = toCents(last.amount) - toCents(prev.amount);
      if (delta !== 0n) {
        push({
          id: `alr-price-${c.id}`,
          kind: delta > 0n ? 'price_increase' : 'price_decrease',
          severity: delta > 0n ? 'warn' : 'info',
          commitment_id: c.id,
          title: `${c.name}: ${prev.amount} → ${last.amount}`,
          body:
            delta > 0n
              ? `El cargo subió ${fromCents(delta)} ${last.currency} respecto al anterior.`
              : `El cargo bajó ${fromCents(-delta)} ${last.currency}.`,
          old_amount: prev,
          new_amount: last,
          due: c.next_due,
          explain: explain('Comparación con el cargo anterior del mismo comercio.', [
            { label: 'Anterior', formula: history[history.length - 2].date, value: prev.amount },
            { label: 'Actual', formula: history[history.length - 1].date, value: last.amount },
            { label: 'Diferencia', formula: 'actual − anterior', value: fromCents(delta) },
          ]),
        });
      }
    }

    if (c.trial_ends) {
      const days = Math.round((parse(c.trial_ends).getTime() - TODAY.getTime()) / D);
      if (days >= 0 && days <= 7) {
        push({
          id: `alr-trial-${c.id}`,
          kind: 'trial_ending',
          severity: 'urgent',
          commitment_id: c.id,
          title: `${c.name}: la prueba termina en ${days} días`,
          body: `Si no la cancelas antes del ${c.trial_ends} te cobrarán ${c.amount.amount} ${c.amount.currency}.`,
          new_amount: c.amount,
          due: c.trial_ends,
        });
      }
    }

    if (c.cadence === 'annual') {
      const days = Math.round((parse(c.next_due).getTime() - TODAY.getTime()) / D);
      if (days >= 0 && days <= 45) {
        push({
          id: `alr-annual-${c.id}`,
          kind: 'annual_renewal',
          severity: 'info',
          commitment_id: c.id,
          title: `${c.name} se renueva en ${days} días`,
          body: `Cargo anual de ${c.amount.amount} ${c.amount.currency} el ${c.next_due}.`,
          new_amount: c.amount,
          due: c.next_due,
        });
      }
    }
  }

  for (const [key, mark] of Object.entries(ORG.marks)) {
    if (mark.status !== 'missed') continue;
    const [cid, due] = key.split('|');
    const c = byId(cid);
    if (!c) continue;
    push({
      id: `alr-missed-${cid}-${due}`,
      kind: 'missed_payment',
      severity: 'urgent',
      commitment_id: cid,
      title: `${c.name}: no encontramos el pago del ${due}`,
      body: 'Venció hace más de 3 días y no hay ningún movimiento que lo respalde.',
      new_amount: c.amount,
      due,
    });
  }

  // Duplicates: two active commitments sharing a category hint.
  const groups: Record<string, Commitment[]> = {};
  for (const c of ORG.commitments) {
    if (!active(c) || !c.category_hint) continue;
    (groups[c.category_hint] ??= []).push(c);
  }
  for (const [hint, list] of Object.entries(groups)) {
    if (list.length < 2) continue;
    push({
      id: `alr-dup-${hint}`,
      kind: 'duplicate',
      severity: 'info',
      commitment_id: list[0].id,
      title: `${list.map((c) => c.name).join(' + ')}: dos servicios de ${hint}`,
      body: `Juntos suman ${sum(list.map((c) => c.amount.amount))} MXN al mes.`,
      new_amount: amt(sum(list.map((c) => c.amount.amount))),
    });
  }

  const prime = byId('cmt-prime');
  if (prime) {
    push({
      id: 'alr-forgotten-cmt-prime',
      kind: 'forgotten',
      severity: 'info',
      commitment_id: prime.id,
      title: `${prime.name}: no lo has revisado en 11 meses`,
      body: 'Es un cargo anual. Revísalo antes de que se renueve solo.',
      new_amount: prime.amount,
      due: prime.next_due,
    });
  }

  const order: Record<OrgAlert['severity'], number> = { urgent: 0, warn: 1, info: 2 };
  return out.sort((a, b) => order[a.severity] - order[b.severity]);
}

/* -------------------------------------------------------------- calendar --- */

export function orgCalendar(from: string, to: string): OrganizerCalendar {
  const days: Record<string, { items: OrganizerCalendar['days'][number]['items']; out: bigint; inn: bigint }> = {};
  for (let d = parse(from); iso(d) <= to; d = addDays(d, 1)) {
    days[iso(d)] = { items: [], out: 0n, inn: 0n };
  }
  for (const c of ORG.commitments) {
    if (c.status === 'cancelled') continue;
    for (const due of duesBetween(c, from, to)) {
      const slot = days[due];
      if (!slot) continue;
      const a = occurrenceAmount(c, due);
      const st = occurrenceStatus(c, due);
      slot.items.push({
        kind: c.kind === 'income' ? 'income' : c.kind === 'loan_payment' ? 'loan' : 'commitment',
        date: due,
        id: c.id,
        name: c.name,
        amount: a,
        status: st,
        txn_id: ORG.marks[`${c.id}|${due}`]?.txn_id ?? null,
        commitment_kind: c.kind,
        account_id: c.account_id ?? null,
        account_name: c.account_name ?? null,
        entry_id: ORG.marks[`${c.id}|${due}`]?.entry_id ?? null,
      });
      if (st === 'skipped') continue;
      if (outflow(c)) slot.out += toCents(a.amount);
      else slot.inn += toCents(a.amount);
    }
  }
  return {
    days: Object.entries(days).map(([date, v]) => ({
      date,
      items: v.items,
      total_out: centsAmt(v.out),
      total_in: centsAmt(v.inn),
    })),
    explain: explain('Cargos proyectados, tarjetas, créditos e ingresos del periodo.'),
  };
}

/** Legacy positional mark (kept for the old route); statuses restricted to paid|skipped. */
export function orgMark(cid: string, due: string, status: OccurrenceStatus, txn_id?: string | null) {
  ORG.marks[`${cid}|${due}`] = { status, txn_id: txn_id ?? `txn-manual-${cid}-${due}` };
  return { ok: true };
}

/**
 * POST /occurrences/mark: link the given entry, else find a matching one (commitment_id
 * link, then payee ±3 d ±10 %), else — when `log_entry` — create the pf entry stamped with
 * `commitment_id`. Idempotent: marking again returns the same entry_id.
 */
export function orgMarkBody(body: MarkOccurrenceBody): MarkOccurrenceResult {
  const c = byId(body.commitment_id);
  if (!c) throw detailError(404, `commitment ${body.commitment_id} not found`);
  if (body.status !== 'paid' && body.status !== 'skipped') {
    throw new MockBadStatus();
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(body.date)) throw detailError(422, 'date must be YYYY-MM-DD');
  const key = `${c.id}|${body.date}`;
  const prev = ORG.marks[key];
  let entryId: string | null = prev?.entry_id ?? null;
  let autoCreated = prev?.auto_created ?? false;
  if (body.status === 'paid') {
    if (body.entry_id) {
      const found = PF5.entries.find((e) => e.id === body.entry_id && !e.voided);
      if (!found) throw detailError(404, `entry ${body.entry_id} not found`);
      entryId = found.id;
      autoCreated = false;
    } else if (!entryId) {
      const amountStr = body.amount?.amount ?? occurrenceAmount(c, body.date).amount;
      const match = pfFindMatchingEntry(c.id, c.name, body.date, amountStr);
      if (match) {
        entryId = match.id;
        autoCreated = false;
      } else if (body.log_entry) {
        const accountId = body.account_id ?? c.account_id;
        if (!accountId) throw detailError(400, 'Primero agrega una cuenta');
        const created = pfCreateEntry(
          {
            kind: c.kind === 'income' ? 'income' : 'expense',
            date: body.date,
            amount: body.amount ?? occurrenceAmount(c, body.date),
            account_id: accountId,
            label_id: c.label_id ?? null,
            payee: c.name,
            tags: ['pago-fijo'],
            commitment_id: c.id,
          },
          'organizer',
        );
        entryId = created.id;
        autoCreated = true;
      }
    }
  }
  const amount = body.amount ?? occurrenceAmount(c, body.date);
  ORG.marks[key] = {
    status: body.status,
    txn_id: entryId ? `txn-${entryId}` : prev?.txn_id ?? null,
    entry_id: entryId,
    amount,
    auto_created: autoCreated,
  };
  return {
    occurrence: {
      commitment_id: c.id,
      due: body.date,
      status: body.status,
      txn_id: ORG.marks[key].txn_id ?? null,
      amount,
      entry_id: entryId,
      auto_created: autoCreated,
    },
    entry_id: entryId,
  };
}

class MockBadStatus extends Error {
  constructor() {
    super('status must be paid or skipped');
  }
}

/** DELETE /occurrences/mark: forget the mark; void the auto-created entry when untouched. */
export function orgUnmark(cid: string, date: string): UnmarkOccurrenceResult {
  const key = `${cid}|${date}`;
  const prev = ORG.marks[key];
  if (!prev) return { removed: false, voided_entry_id: null };
  delete ORG.marks[key];
  let voided: string | null = null;
  if (prev.auto_created && prev.entry_id && pfEntryUntouched(prev.entry_id)) {
    pfDeleteEntry(prev.entry_id);
    voided = prev.entry_id;
  }
  return { removed: true, voided_entry_id: voided };
}

/* ------------------------------------------------------------------ plan --- */

const PLAN_ITEMS: { group: Essential; key: string; name: string; planned: string; actual: string }[] = [
  { group: 'needs', key: 'lbl-d92e338efc65', name: 'Renta/Hipoteca', planned: '12000.00', actual: '12000.00' },
  { group: 'needs', key: 'lbl-6c72269a8eab', name: 'Súper', planned: '6000.00', actual: '5210.75' },
  { group: 'needs', key: 'cmt-telcel', name: 'Telcel', planned: '399.00', actual: '399.00' },
  { group: 'needs', key: 'cmt-cfe', name: 'CFE', planned: '1120.00', actual: '1120.00' },
  { group: 'wants', key: 'lbl-569885caff5c', name: 'Comida fuera', planned: '3500.00', actual: '2890.00' },
  { group: 'wants', key: 'cmt-netflix', name: 'Netflix', planned: '219.00', actual: '219.00' },
  { group: 'wants', key: 'cmt-spotify', name: 'Spotify', planned: '129.00', actual: '129.00' },
  { group: 'wants', key: 'cmt-gym', name: 'Smart Fit', planned: '649.00', actual: '0.00' },
  { group: 'wants', key: 'cmt-icloud', name: 'iCloud+', planned: '49.00', actual: '49.00' },
  { group: 'savings', key: 'goal-emergencia', name: 'Fondo de emergencia', planned: '5000.00', actual: '5000.00' },
  { group: 'debt', key: 'cmt-auto', name: 'Crédito auto', planned: '5000.00', actual: '5000.00' },
];

export function orgPlan(): OrganizerPlan {
  const groups: PlanGroup[] = (['needs', 'wants', 'savings', 'debt'] as Essential[]).map((g) => {
    const items: PlanItem[] = PLAN_ITEMS.filter((i) => i.group === g).map((i) => {
      const planned = ORG.planSeeded ? (ORG.planned[i.key] ?? i.planned) : (ORG.planned[i.key] ?? '0.00');
      const left = fromCents(toCents(planned) - toCents(i.actual));
      const plannedCents = toCents(planned);
      return {
        label_id: i.key.startsWith('lbl-') ? i.key : null,
        commitment_id: i.key.startsWith('cmt-') ? i.key : null,
        name: i.name,
        planned: amt(planned),
        actual: amt(i.actual),
        left: amt(left),
        pct: plannedCents === 0n ? '0' : (Number(toCents(i.actual)) / Number(plannedCents)).toFixed(4),
      };
    });
    const planned = sum(items.map((i) => i.planned.amount));
    const actual = sum(items.map((i) => i.actual.amount));
    return {
      group: g,
      planned: amt(planned),
      actual: amt(actual),
      left: amt(fromCents(toCents(planned) - toCents(actual))),
      items,
    };
  });

  const incomeExpected = '50000.00';
  const incomeActual = '50000.00';
  const spent = sum(groups.filter((g) => g.group !== 'savings').map((g) => g.actual.amount));
  const savedCents = toCents(incomeActual) - toCents(spent);
  const rate = (Number(savedCents) / Number(toCents(incomeActual))).toFixed(4);

  return {
    period: TODAY_ISO.slice(0, 7),
    groups,
    income_expected: amt(incomeExpected),
    income_actual: amt(incomeActual),
    savings_rate: rate,
    uncategorized: ORG.uncategorized.map((u) => ({ ...u })),
    explain: explain('Plan de sobres: lo planeado contra lo que realmente gastaste este mes.', [
      { label: 'Ingreso real', formula: null, value: incomeActual },
      { label: 'Gasto (sin ahorro)', formula: 'needs + wants + debt', value: spent },
      { label: 'Ahorrado', formula: 'ingreso − gasto', value: fromCents(savedCents) },
    ]),
  };
}

export function orgAutoPlan(months: number): OrganizerPlan {
  ORG.planSeeded = true;
  for (const i of PLAN_ITEMS) ORG.planned[i.key] = i.planned;
  const p = orgPlan();
  p.explain = explain(`Propuesta a partir del promedio de tus últimos ${months} meses y tus compromisos.`, [
    { label: 'Meses promediados', formula: null, value: String(months) },
    { label: 'Planeado total', formula: 'needs + wants + savings + debt', value: sum(p.groups.map((g) => g.planned.amount)) },
  ]);
  return p;
}

export function orgPutPlan(items: { label_id: string; planned: string }[]): OrganizerPlan {
  ORG.planSeeded = true;
  for (const i of items) ORG.planned[i.label_id] = i.planned;
  return orgPlan();
}

export function orgOrganize(assign: OrganizeAssignment[]): OrganizeResult {
  let rules = 0;
  for (const a of assign) {
    const txn = ORG.uncategorized.find((u) => u.txn_id === a.txn_id);
    ORG.uncategorized = ORG.uncategorized.filter((u) => u.txn_id !== a.txn_id);
    if (a.create_rule && txn) {
      rules += 1;
      ORG.rules.push({
        id: nid('rul'),
        pattern: txn.payee.split(/[ *]/)[0],
        label_id: a.label_id,
        label_name: null,
        created_at: TODAY_ISO,
      });
    }
  }
  return {
    assigned: assign.length,
    rules_created: rules,
    explain: explain(`${assign.length} movimientos reetiquetados en el libro mayor.`),
  };
}

/* ---------------------------------------------------------------- quickadd - */

const CADENCE_WORDS: [RegExp, Cadence][] = [
  [/\b(semanal|weekly|cada semana)\b/i, 'weekly'],
  [/\b(quincenal|biweekly|cada quincena)\b/i, 'biweekly'],
  [/\b(bimestral|bimonthly)\b/i, 'bimonthly'],
  [/\b(trimestral|quarterly)\b/i, 'quarterly'],
  [/\b(semestral|semiannual)\b/i, 'semiannual'],
  [/\b(anual|annual|yearly|al año)\b/i, 'annual'],
  [/\b(mensual|monthly|al mes)\b/i, 'monthly'],
];

const KIND_WORDS: [RegExp, CommitmentKind][] = [
  [/\b(renta|rent|alquiler)\b/i, 'rent'],
  [/\b(seguro|insurance)\b/i, 'insurance'],
  [/\b(cr[eé]dito|loan|pr[eé]stamo)\b/i, 'loan_payment'],
  [/\b(luz|agua|gas|cfe|utility)\b/i, 'utility'],
  [/\b(recibo|bill|tel[eé]fono|internet)\b/i, 'bill'],
  [/\b(sueldo|n[oó]mina|salary|income|ingreso)\b/i, 'income'],
];

export function orgQuickAdd(text: string, save: boolean): QuickAddPreview {
  const raw = text.trim();
  const warnings: string[] = [];

  const currency = /\busd\b/i.test(raw) ? 'USD' : MXN;
  const amountMatch = raw.match(/(\d[\d,]*(?:\.\d{1,2})?)/);
  const amount = amountMatch ? amountMatch[1].replace(/,/g, '') : '0';
  if (!amountMatch) warnings.push('No encontramos un importe en la línea.');

  let cadence: Cadence = 'monthly';
  let interval: number | null = null;
  const every = raw.match(/cada\s+(\d{1,3})\s*d[ií]as?/i) ?? raw.match(/every\s+(\d{1,3})\s*days?/i);
  if (every) {
    cadence = 'custom';
    interval = Number(every[1]);
  } else {
    for (const [re, c] of CADENCE_WORDS) {
      if (re.test(raw)) {
        cadence = c;
        break;
      }
    }
  }

  const dayMatch =
    raw.match(/d[ií]a\s+(\d{1,2})/i) ?? raw.match(/\bel\s+(\d{1,2})\b/i) ?? raw.match(/on the\s+(\d{1,2})/i);
  const day = dayMatch ? Math.min(28, Number(dayMatch[1])) : TODAY.getUTCDate();

  const trialMatch = raw.match(/(?:prueba hasta|trial until)\s+(\d{4}-\d{2}-\d{2})/i);

  let kind: CommitmentKind = 'subscription';
  for (const [re, k] of KIND_WORDS) {
    if (re.test(raw)) {
      kind = k;
      break;
    }
  }

  // The name is the leading words before the number.
  const head = amountMatch ? raw.slice(0, raw.indexOf(amountMatch[1])) : raw;
  const name = (head.trim() || raw.split(/\s+/)[0] || 'Nuevo cargo').replace(/\b\w/g, (m) => m.toUpperCase());

  const commitment: Commitment = {
    id: save ? nid('cmt') : 'cmt-preview',
    ws_id: WS_ID,
    kind,
    name,
    merchant_patterns: [name.toUpperCase()],
    amount: amt(amount.includes('.') ? amount : `${amount}.00`, currency),
    amount_variable: false,
    cadence,
    interval_days: interval,
    anchor_day: cadence === 'custom' || cadence === 'weekly' || cadence === 'biweekly' ? null : day,
    weekday: null,
    next_due: cadence === 'custom' ? iso(addDays(TODAY, interval ?? 30)) : nextDayOfMonth(day),
    account: 'Assets:Bank:BBVA',
    label_id: null,
    essential: kind === 'rent' || kind === 'utility' || kind === 'bill' ? 'needs' : kind === 'loan_payment' ? 'debt' : 'wants',
    status: trialMatch ? 'trial' : 'active',
    trial_ends: trialMatch ? trialMatch[1] : null,
    started: TODAY_ISO,
    ended: null,
    auto_pay: true,
    cancel_notes: null,
    linked_loan_id: null,
    linked_card_id: null,
    source: 'manual',
    confidence: amountMatch ? 0.9 : 0.4,
    last_seen: null,
    notes: null,
    category_hint: null,
    explain: explain(`Interpretamos «${raw}».`, [
      { label: 'Importe', formula: 'número de la línea', value: amount },
      { label: 'Frecuencia', formula: cadence === 'custom' ? `cada ${interval} días` : cadence, value: '1' },
      { label: 'Próximo cobro', formula: dayMatch ? `día ${day}` : 'hoy', value: '1' },
    ]),
  };

  if (save) ORG.commitments.push(withEquivalents(commitment));
  const autoLabel = kind === 'rent' ? 'lbl-d92e338efc65' : null;
  if (warnings.length > 0) {
    commitment.explain = explain(commitment.explain?.summary ?? '', [
      ...(commitment.explain?.steps ?? []),
      { label: 'warnings', formula: null, value: warnings.join('; ') },
    ]);
  }
  return { preview: withEquivalents(commitment), saved: save, auto_label: autoLabel, explain: commitment.explain };
}

/* ------------------------------------------------------------------ CRUD --- */

export function orgList(kind?: string | null, status?: string | null): Commitment[] {
  return ORG.commitments.filter(
    (c) => (!kind || c.kind === kind) && (!status || c.status === status),
  );
}

export function orgDetail(id: string): CommitmentDetail | null {
  const c = byId(id);
  if (!c) return null;
  const occurrences: Occurrence[] = [];
  let cursor = c.next_due;
  for (let i = 0; i < 12; i += 1) {
    cursor = retreat(cursor, c);
    occurrences.push(occurrence(c, cursor));
  }
  const detail: CommitmentDetail = {
    ...c,
    price_history: PRICE_HISTORY[c.id] ?? [{ date: c.started ?? TODAY_ISO, amount: c.amount }],
    occurrences,
  };
  if (c.linked_loan_id) {
    detail.loan = {
      loan_id: c.linked_loan_id,
      name: 'Crédito auto',
      payments_made: 8,
      payments_total: 48,
      months_left: 40,
      paid: amt('40000.00'),
      remaining: amt('140000.00'),
      principal: amt('180000.00'),
      payment: c.amount,
    };
  }
  return detail;
}

function applyInput(c: Commitment, body: Partial<CommitmentInput>): Commitment {
  return {
    ...c,
    ...body,
    amount: body.amount ? { amount: String(body.amount.amount), currency: body.amount.currency } : c.amount,
    merchant_patterns: body.merchant_patterns ?? c.merchant_patterns,
  } as Commitment;
}

export function orgCreate(body: CommitmentInput): Commitment {
  const c: Commitment = {
    id: nid('cmt'),
    ws_id: WS_ID,
    merchant_patterns: [],
    amount_variable: false,
    interval_days: null,
    anchor_day: null,
    weekday: null,
    label_id: null,
    status: 'active',
    trial_ends: null,
    started: TODAY_ISO,
    ended: null,
    auto_pay: true,
    cancel_notes: null,
    linked_loan_id: null,
    linked_card_id: null,
    source: 'manual',
    confidence: 1,
    last_seen: null,
    notes: null,
    category_hint: null,
    explain: explain('Capturado a mano.'),
    ...body,
  } as Commitment;
  const withEq = withEquivalents(withAccount(c));
  ORG.commitments.push(withEq);
  return withEq;
}

export function orgUpdate(id: string, body: Partial<CommitmentInput>): Commitment | null {
  const i = ORG.commitments.findIndex((c) => c.id === id);
  if (i < 0) return null;
  ORG.commitments[i] = withEquivalents(withAccount(applyInput(ORG.commitments[i], body)));
  return ORG.commitments[i];
}

export function orgSetStatus(id: string, status: CommitmentStatus, notes?: string | null): Commitment | null {
  const c = byId(id);
  if (!c) return null;
  c.status = status;
  if (status === 'cancelled') {
    c.ended = TODAY_ISO;
    c.cancel_notes = notes ?? c.cancel_notes;
  }
  return c;
}

/* ----------------------------------------------------------------- detect -- */

const CANDIDATE_SEEDS: { name: string; pattern: string; amount: string; cadence: Cadence; day: number; kind: CommitmentKind; conf: number; essential: Essential }[] = [
  { name: 'YouTube Premium', pattern: 'GOOGLE *YOUTUBEPREMIUM', amount: '199.00', cadence: 'monthly', day: 9, kind: 'subscription', conf: 0.94, essential: 'wants' },
  { name: 'Totalplay', pattern: 'TOTALPLAY 4471', amount: '699.00', cadence: 'monthly', day: 24, kind: 'bill', conf: 0.91, essential: 'needs' },
  { name: 'Agua y Drenaje', pattern: 'AGUA Y DRENAJE', amount: '310.00', cadence: 'monthly', day: 18, kind: 'utility', conf: 0.79, essential: 'needs' },
  { name: 'ChatGPT Plus', pattern: 'OPENAI *CHATGPT SUBSCR', amount: '410.00', cadence: 'monthly', day: 6, kind: 'subscription', conf: 0.88, essential: 'wants' },
  { name: 'Seguro auto GNP', pattern: 'GNP SEGUROS', amount: '2450.00', cadence: 'semiannual', day: 28, kind: 'insurance', conf: 0.72, essential: 'needs' },
];

function makeCandidates(): Candidate[] {
  return CANDIDATE_SEEDS.map((s, i) => {
    const c = seedToCommitment({
      id: `cand-cmt-${i + 1}`,
      kind: s.kind,
      name: s.name,
      patterns: [s.pattern],
      amount: s.amount,
      cadence: s.cadence,
      day: s.day,
      account: 'Assets:Bank:BBVA',
      essential: s.essential,
      confidence: s.conf,
    });
    return {
      id: `cand-${i + 1}`,
      merchant: s.pattern,
      preview: c,
      confidence: s.conf,
      status: 'open',
      evidence: [1, 2, 3].map((n) => ({
        date: dayOfMonth(s.day, -n),
        amount: amt(s.amount),
        description: `${s.pattern} ${dayOfMonth(s.day, -n).slice(5)}`,
        source: 'bank',
      })),
    };
  });
}

const PAYDAYS: Payday[] = [
  { date: nextDayOfMonth(5), amount: amt('25000.00'), cadence: 'monthly' },
  { date: nextDayOfMonth(20), amount: amt('25000.00'), cadence: 'monthly' },
];

export function orgDetect(): DetectResult {
  if (ORG.candidates.length === 0) ORG.candidates = makeCandidates();
  const candidates = ORG.candidates.filter((c) => !ORG.dismissedCandidates.has(c.id));
  return {
    candidates,
    count: candidates.length,
    explain: explain('Agrupamos tus movimientos por comercio normalizado y buscamos periodos regulares.', [
      { label: 'Candidatos', formula: '≥2 cargos con intervalo estable', value: String(ORG.candidates.length) },
    ]),
  };
}

export function orgAcceptCandidate(id: string, overrides?: Partial<CommitmentInput>): Commitment | null {
  const cand = ORG.candidates.find((c) => c.id === id);
  if (!cand) return null;
  const c: Commitment = withEquivalents({ ...(cand.preview as Commitment), id: nid('cmt'), source: 'detected' });
  ORG.commitments.push(overrides ? applyInput(c, overrides) : c);
  ORG.candidates = ORG.candidates.filter((x) => x.id !== id);
  return c;
}

export function orgDismissCandidate(id: string) {
  ORG.dismissedCandidates.add(id);
  ORG.candidates = ORG.candidates.filter((c) => c.id !== id);
  return { ok: true };
}

export function orgSetupStatus(): SetupStatus {
  const hasBankLines = true;
  const hasCommitments = ORG.commitments.length > 0;
  const hasIncome = ORG.commitments.some((c) => c.kind === 'income');
  const hasPlan = ORG.planSeeded;
  const steps = [hasBankLines, hasCommitments, hasIncome, hasPlan];
  const done = steps.filter(Boolean).length;
  return {
    has_bank_lines: hasBankLines,
    has_commitments: hasCommitments,
    has_income: hasIncome,
    has_plan: hasPlan,
    counts: {
      bank_lines: 184,
      commitments: ORG.commitments.length,
      income_commitments: ORG.commitments.filter((c) => c.kind === 'income').length,
      budgets: PLAN_ITEMS.length,
      open_candidates: ORG.candidates.filter((c) => !ORG.dismissedCandidates.has(c.id)).length,
    },
    progress: `${done}/${steps.length}`,
    explain: explain('Configuración en 3 pasos: movimientos bancarios → compromisos detectados → plan.'),
  };
}

export function orgSetupRun(months: number): SetupRunResult {
  ORG.setupRan = true;
  const detected = orgDetect();
  return {
    status: orgSetupStatus(),
    detected: detected.candidates.length,
    planned: PLAN_ITEMS.length,
    candidates: detected.candidates,
    paydays: PAYDAYS,
    plan: {
      groups: (['needs', 'wants', 'savings', 'debt'] as Essential[]).map((g) => ({
        group: g,
        planned: amt(sum(PLAN_ITEMS.filter((i) => i.group === g).map((i) => i.planned))),
      })),
      income_expected: amt('50000.00'),
    },
    explain: explain(`Analizamos tus últimos ${months} meses de movimientos.`),
  };
}
