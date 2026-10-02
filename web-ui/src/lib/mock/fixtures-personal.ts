/**
 * Mock fixtures + in-memory behaviour for the personal side (entries envelope + keyset cursor +
 * totals, void semantics, liability sign, partial stream PUT with real history rows, the
 * onboarding step ids).
 *
 * Live like `fixtures-organizer`: a tiny working implementation, not a canned payload, because the
 * whole point of these screens is that a person can *do* things. Creating an account really makes
 * it pickable in Agregar; logging an expense really moves that account's balance and shows up
 * in Movimientos; deleting really voids it (and a second delete really answers 409).
 *
 * Money discipline holds: every amount is a decimal *string*, and sums are done in integer
 * centavos with BigInt (the mock's stand-in for the API's `Decimal`). No float ever produces
 * a figure the UI displays. Dates are LOCAL: "today" is never `toISOString()`.
 */
import type { Amount } from '../types';
import type {
  EntriesPage,
  Entry,
  EntryInput,
  EntryKind,
  EntrySource,
  IncomeStream,
  IncomeStreamInput,
  Onboarding,
  PfAccount,
  PfAccountAdjust,
  PfAccountInput,
  PfAccountType,
  StreamCadence,
  StreamHistoryRow,
} from '../types-personal';

/* ----------------------------------------------------------------- errors */

/** An HTTP failure a fixture wants the router to answer with a specific body. */
export class MockHttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(typeof body === 'string' ? body : JSON.stringify(body));
    this.name = 'MockHttpError';
  }
}

/** FastAPI's `{detail: "…"}`. */
export const detailError = (status: number, detail: string) => new MockHttpError(status, { detail });

/** pydantic's 422 array for one field. */
export const pydanticError = (loc: (string | number)[], msg: string, type = 'value_error') =>
  new MockHttpError(422, { detail: [{ loc, msg, type }] });

/* ----------------------------------------------------------------- dates */

const pad2 = (n: number) => String(n).padStart(2, '0');
/** Local calendar date as ISO — the only "today" the mock knows. */
export const localIso = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const todayLocalIso = () => localIso(new Date());
const TODAY = new Date();
const TODAY_ISO = todayLocalIso();
const shiftDays = (n: number) => {
  const d = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() + n);
  return localIso(d);
};
const daysAgo = (n: number) => shiftDays(-n);
const daysAhead = (n: number) => shiftDays(n);
export const currentPeriodLocal = () => TODAY_ISO.slice(0, 7);

/* ------------------------------------------------------------- decimals */

export function toCents(decimal: string): bigint {
  const s = (decimal ?? '0').trim();
  const neg = s.startsWith('-');
  const [int = '0', frac = ''] = s.replace(/^[+-]/, '').split('.');
  const cents = BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2));
  return neg ? -cents : cents;
}

export function fromCents(cents: bigint): string {
  const neg = cents < 0n;
  const abs = neg ? -cents : cents;
  return `${neg ? '-' : ''}${abs / 100n}.${(abs % 100n).toString().padStart(2, '0')}`;
}

const CURRENCY = 'MXN';
const money = (amount: string, currency = CURRENCY): Amount => ({ amount, currency });

/** "36.9" → "0.369" as strings (the API stores the fraction, returns both). */
export function percentToFraction(pct: string): string {
  const [int = '0', frac = ''] = pct.trim().split('.');
  const digits = (int + frac).replace(/^0+/, '') || '0';
  const fracLen = frac.length + 2;
  const padded = digits.padStart(fracLen + 1, '0');
  const whole = padded.slice(0, padded.length - fracLen);
  const rest = padded.slice(padded.length - fracLen).replace(/0+$/, '');
  return rest ? `${whole}.${rest}` : whole;
}

/** "0.369" → "36.9". */
export function fromFraction(fraction: string): string {
  const [int = '0', frac = ''] = fraction.trim().split('.');
  const f = frac + '00';
  const out = `${int}${f.slice(0, 2)}`.replace(/^0+(?=\d)/, '');
  const rest = f.slice(2).replace(/0+$/, '');
  return rest ? `${out}.${rest}` : out;
}

/* ---------------------------------------------------------- ledger names */

/** "BBVA nómina" → "BBVANomina" — the slug the API would build for the ledger account. */
function slug(name: string): string {
  const plain = name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9 ]/g, ' ');
  return plain
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join('');
}

function ledgerAccount(type: PfAccountType, name: string): string {
  const s = slug(name) || 'Cuenta';
  switch (type) {
    case 'cash':
      return 'Assets:Cash';
    case 'credit_card':
      return `Liabilities:CreditCard:${s}`;
    case 'loan':
      return `Liabilities:Loans:${s}`;
    case 'investment':
      return `Assets:Investments:${s}`;
    case 'savings':
    case 'checking':
    default:
      return `Assets:Bank:${s}`;
  }
}

export const isLiability = (type: PfAccountType) => type === 'credit_card' || type === 'loan';

/* -------------------------------------------------------------- the state */

let seq = 1;
const nid = (p: string) => `${p}-${(seq += 1).toString(36)}${Date.now().toString(36).slice(-3)}`;

interface AccountRec extends PfAccount {
  /** Ledger-signed opening balance (liabilities negative). */
  opening_cents: bigint;
}

/**
 * Three accounts and a handful of movements, so the demo build has something to show — but
 * the screens are all written for the zero-state too. The card's opening is typed as what is
 * OWED (positive); the "server" negates it on write.
 */
const ACCOUNT_SEED: { name: string; type: PfAccountType; institution: string | null; opening: string }[] = [
  { name: 'BBVA', type: 'checking', institution: 'BBVA México', opening: '123217.50' },
  { name: 'Efectivo', type: 'cash', institution: null, opening: '3840.00' },
  { name: 'Tarjeta Banorte', type: 'credit_card', institution: 'Banorte', opening: '8420.00' },
];

function makeAccount(a: PfAccountInput): AccountRec {
  const typed = a.opening_balance?.amount ?? '0.00';
  const owedInput = isLiability(a.type);
  if (owedInput && toCents(typed) < 0n) {
    throw pydanticError(['body', 'opening_balance'], 'Input should be greater than or equal to 0');
  }
  const openingCents = owedInput ? -toCents(typed) : toCents(typed);
  const currency = a.currency ?? CURRENCY;
  const aprPercent = a.apr_percent ?? null;
  const apr = aprPercent ? percentToFraction(aprPercent) : (a.apr ?? null);
  const ledger = ledgerAccount(a.type, a.name);
  return {
    id: nid('acct'),
    name: a.name,
    type: a.type,
    institution: a.institution ?? null,
    currency,
    account: ledger,
    ledger_account: ledger,
    opening_balance: money(fromCents(openingCents), currency),
    opening_date: a.opening_date ?? TODAY_ISO,
    credit_limit: a.credit_limit ?? null,
    cut_day: a.cut_day ?? null,
    due_day: a.due_day ?? null,
    apr,
    apr_percent: aprPercent ?? (apr ? fromFraction(apr) : null),
    loan_months: a.loan_months ?? null,
    loan_principal: a.loan_principal ?? null,
    archived: false,
    opening_cents: openingCents,
  };
}


const accounts: AccountRec[] = ACCOUNT_SEED.map((s) =>
  makeAccount({
    name: s.name,
    type: s.type,
    institution: s.institution,
    currency: CURRENCY,
    opening_balance: money(s.opening),
    opening_date: daysAgo(60),
    ...(s.type === 'credit_card'
      ? { credit_limit: money('60000.00'), cut_day: 4, due_day: 22, apr_percent: '36.9' }
      : {}),
  }),
);

interface EntryRec {
  id: string;
  date: string;
  kind: EntryKind;
  cents: bigint;
  currency: string;
  account_id: string;
  to_account_id: string | null;
  label_id: string | null;
  payee: string | null;
  note: string | null;
  tags: string[];
  splits: { label_id: string; amount: Amount; note?: string | null }[] | null;
  source: EntrySource;
  editable: boolean;
  non_editable_reason: string | null;
  commitment_id: string | null;
  voided: boolean;
  /** Set once a PUT touched the row (an un-mark only voids untouched auto-created entries). */
  edited: boolean;
  txn_id: string;
}

/** Label ids come from the workspace's own label list (fixtures.ts LABELS). */
const SEED_LABELS = {
  dining: 'lbl-569885caff5c',
  groceries: 'lbl-6c72269a8eab',
  rent: 'lbl-d92e338efc65',
  salary: 'lbl-inc-salary',
};

const seedEntry = (partial: Partial<EntryRec> & Pick<EntryRec, 'date' | 'kind' | 'cents' | 'account_id'>): EntryRec => {
  const id = nid('ent');
  return {
    currency: CURRENCY,
    to_account_id: null,
    label_id: null,
    payee: null,
    note: null,
    tags: [],
    splits: null,
    source: 'manual',
    editable: true,
    non_editable_reason: null,
    commitment_id: null,
    voided: false,
    edited: false,
    txn_id: `txn-${id}`,
    ...partial,
    id,
  };
};

/** The paydays (15th/30th, clamped) on or before today, newest first — the seed incomes land on them. */
function pastPaydays(anchors: number[], count: number): string[] {
  const out: string[] = [];
  for (let back = 0; back < 4 && out.length < count; back += 1) {
    const y = TODAY.getFullYear();
    const m = TODAY.getMonth() - back;
    const last = new Date(y, m + 1, 0).getDate();
    const dues = anchors.map((d) => localIso(new Date(y, m, Math.min(d, last)))).filter((d) => d <= TODAY_ISO);
    for (const d of dues.sort().reverse()) if (out.length < count) out.push(d);
  }
  return out;
}
const PAYDAYS = pastPaydays([15, 30], 3);
const quincena = (date: string) =>
  seedEntry({ date, kind: 'income', cents: toCents('22500.00'), account_id: accounts[0].id, label_id: SEED_LABELS.salary, payee: 'Quincena', source: 'payroll', editable: false, non_editable_reason: 'source:payroll' });

const entries: EntryRec[] = [
  seedEntry({ date: daysAgo(1), kind: 'expense', cents: toCents('-320.00'), account_id: accounts[0].id, label_id: SEED_LABELS.dining, payee: 'Taquería El Rey' }),
  seedEntry({ date: daysAgo(3), kind: 'expense', cents: toCents('-1875.40'), account_id: accounts[0].id, label_id: SEED_LABELS.groceries, payee: 'HEB', note: 'Despensa de la semana', tags: ['casa'], source: 'import' }),
  seedEntry({ date: daysAgo(6), kind: 'expense', cents: toCents('-12500.00'), account_id: accounts[0].id, label_id: SEED_LABELS.rent, payee: 'Renta departamento', source: 'organizer', commitment_id: 'cmt-renta' }),
  quincena(PAYDAYS[0]),
  seedEntry({ date: daysAgo(9), kind: 'transfer', cents: toCents('-2000.00'), account_id: accounts[0].id, to_account_id: accounts[1].id, payee: 'Retiro cajero' }),
  seedEntry({ date: daysAgo(12), kind: 'expense', cents: toCents('-459.00'), account_id: accounts[2].id, label_id: SEED_LABELS.groceries, payee: 'Soriana' }),
  quincena(PAYDAYS[1]),
  seedEntry({ date: daysAgo(35), kind: 'expense', cents: toCents('-12500.00'), account_id: accounts[0].id, label_id: SEED_LABELS.rent, payee: 'Renta departamento', source: 'organizer', commitment_id: 'cmt-renta' }),
  quincena(PAYDAYS[2]),
];

/** The next 15th/30th-style date from today, for the demo's default stream. */
function nextSemimonthly(days: number[]): string {
  const sorted = [...days].sort((a, b) => a - b);
  const y = TODAY.getFullYear();
  const m = TODAY.getMonth();
  const lastOfMonth = new Date(y, m + 1, 0).getDate();
  for (const d of sorted) {
    const day = Math.min(d, lastOfMonth);
    if (day > TODAY.getDate()) return localIso(new Date(y, m, day));
  }
  const lastNext = new Date(y, m + 2, 0).getDate();
  return localIso(new Date(y, m + 1, Math.min(sorted[0], lastNext)));
}

/** The next expected date for any cadence — good enough for a mock, never a tax figure. */
export function nextExpectedFor(cadence: StreamCadence, anchorDays: number[]): string {
  if (cadence === 'semimonthly' || cadence === 'monthly') {
    return nextSemimonthly(anchorDays.length ? anchorDays : [1]);
  }
  if (cadence === 'weekly') return daysAhead(7);
  if (cadence === 'biweekly') return daysAhead(14);
  if (cadence === 'annual') return daysAhead(365);
  return daysAhead(30);
}

const streams: IncomeStream[] = [
  {
    id: nid('inc'),
    name: 'Sueldo',
    source_type: 'salary',
    amount: money('22500.00'),
    gross_amount: money('27300.00'),
    cadence: 'semimonthly',
    anchor_days: [15, 30],
    weekday: null,
    next_expected: nextSemimonthly([15, 30]),
    account_id: accounts[0].id,
    label_id: SEED_LABELS.salary,
    active: true,
    notes: null,
  },
];

/* ------------------------------------------------------------- accounts */

const live = () => entries.filter((e) => !e.voided);

/** Ledger-signed balance: opening plus every live movement that touches the account. */
function balanceCents(id: string): bigint {
  const acct = accounts.find((a) => a.id === id);
  let cents = acct?.opening_cents ?? 0n;
  for (const e of live()) {
    if (e.account_id === id) cents += e.cents;
    // A transfer's `cents` is negative on the source; the destination gets the mirror.
    if (e.kind === 'transfer' && e.to_account_id === id) cents -= e.cents;
  }
  return cents;
}

function publicAccount(a: AccountRec): PfAccount {
  const { opening_cents: _opening, ...rest } = a;
  void _opening;
  const currency = a.currency ?? CURRENCY;
  const signed = balanceCents(a.id);
  const owed = isLiability(a.type);
  return {
    ...rest,
    balance: money(fromCents(owed ? -signed : signed), currency),
    balance_signed: money(fromCents(signed), currency),
    owed,
    opening_balance: money(fromCents(owed ? -a.opening_cents : a.opening_cents), currency),
  };
}

export function pfListAccounts(includeArchived = false): PfAccount[] {
  return accounts.filter((a) => includeArchived || !a.archived).map(publicAccount);
}

export function pfGetAccount(id: string): PfAccount | null {
  const a = accounts.find((x) => x.id === id);
  return a ? publicAccount(a) : null;
}

/** ΣAssets + ΣLiabilities, signed. */
export function pfNetWorth(): Amount {
  let total = 0n;
  for (const a of accounts) if (!a.archived) total += balanceCents(a.id);
  return money(fromCents(total));
}

export function pfCreateAccount(body: PfAccountInput): PfAccount {
  if (!body?.name?.trim()) throw pydanticError(['body', 'name'], 'String should have at least 1 character');
  if (accounts.some((a) => a.name.trim().toLowerCase() === body.name.trim().toLowerCase() && !a.archived)) {
    throw detailError(409, `account '${body.name}' already exists`);
  }
  const rec = makeAccount(body);
  accounts.push(rec);
  return publicAccount(rec);
}

export function pfUpdateAccount(id: string, body: Partial<PfAccountInput>): PfAccount {
  const i = accounts.findIndex((a) => a.id === id);
  if (i < 0) throw detailError(404, `account ${id} not found`);
  const prev = accounts[i];
  const type = body.type ?? prev.type;
  const name = body.name ?? prev.name;
  const ledger = ledgerAccount(type, name);
  const aprPercent = body.apr_percent ?? (body.apr ? fromFraction(body.apr) : prev.apr_percent ?? null);
  const next: AccountRec = {
    ...prev,
    ...body,
    id: prev.id,
    type,
    name,
    institution: body.institution ?? prev.institution ?? null,
    currency: body.currency ?? prev.currency,
    account: ledger,
    ledger_account: ledger,
    apr_percent: aprPercent,
    apr: aprPercent ? percentToFraction(aprPercent) : null,
    archived: body.archived ?? prev.archived ?? false,
    // The opening balance is only ever moved by `adjust`, never by an edit of the name.
    opening_balance: prev.opening_balance,
    opening_cents: prev.opening_cents,
  };
  accounts[i] = next;
  return publicAccount(next);
}

/** DELETE: archives when nothing but the opening exists, else 409 (`account_has_movements`). */
export function pfDeleteAccount(id: string): PfAccount {
  const i = accounts.findIndex((a) => a.id === id);
  if (i < 0) throw detailError(404, `account ${id} not found`);
  const used = live().some((e) => e.account_id === id || e.to_account_id === id);
  if (used) {
    throw new MockHttpError(409, {
      detail: `account ${id} has movements; archive it instead of deleting, or remove its entries first`,
      hint: 'archive',
    });
  }
  accounts[i] = { ...accounts[i], archived: true };
  return publicAccount(accounts[i]);
}

/** Ajustar saldo: the user types the real balance (liabilities: what is owed, positive). */
export function pfAdjustAccount(id: string, body: PfAccountAdjust): PfAccount {
  const i = accounts.findIndex((a) => a.id === id);
  if (i < 0) throw detailError(404, `account ${id} not found`);
  const a = accounts[i];
  const typed = toCents(body.balance.amount);
  const target = isLiability(a.type) ? -typed : typed;
  const delta = target - balanceCents(id);
  if (delta !== 0n) {
    entries.push(
      seedEntry({
        date: body.date || TODAY_ISO,
        kind: delta > 0n ? 'income' : 'expense',
        cents: delta,
        account_id: id,
        payee: 'Ajuste de saldo',
        note: body.note ?? null,
        tags: ['ajuste'],
        source: 'manual',
      }),
    );
  }
  return publicAccount(accounts[i]);
}

/* -------------------------------------------------------------- entries */

const accountName = (id: string | null | undefined) =>
  (id && accounts.find((a) => a.id === id)?.name) || null;

function publicEntry(e: EntryRec): Entry {
  return {
    id: e.id,
    date: e.date,
    kind: e.kind,
    amount: money(fromCents(e.cents), e.currency),
    account_id: e.account_id,
    account_name: accountName(e.account_id),
    to_account_id: e.to_account_id,
    to_account_name: accountName(e.to_account_id),
    label_id: e.label_id,
    label_name: null, // filled in by index.ts, which owns the label list
    payee: e.payee,
    note: e.note,
    tags: e.tags,
    splits: e.splits ?? null,
    source: e.source,
    attachment: null,
    txn_id: e.txn_id,
    editable: e.editable,
    non_editable_reason: e.non_editable_reason,
    commitment_id: e.commitment_id,
    voided: e.voided,
  };
}

/** Signed centavos: expenses and the source leg of a transfer are negative. */
function signedCents(kind: EntryKind, amount: string): bigint {
  const abs = toCents(amount.replace(/^-/, ''));
  return kind === 'income' ? abs : -abs;
}

/** Newest first, ties broken by id descending — the keyset the cursor walks. */
const byDateDesc = (a: EntryRec, b: EntryRec) =>
  a.date === b.date ? (a.id < b.id ? 1 : a.id > b.id ? -1 : 0) : a.date < b.date ? 1 : -1;

export interface EntryFilter {
  from?: string | null;
  to?: string | null;
  account_id?: string | null;
  label_id?: string | null;
  kind?: string | null;
  q?: string | null;
  limit?: number | null;
  cursor?: string | null;
}

function filtered(q: EntryFilter): EntryRec[] {
  const needle = (q.q ?? '').trim().toLowerCase();
  return live()
    .filter((e) => (!q.from || e.date >= q.from) && (!q.to || e.date <= q.to))
    .filter((e) => !q.account_id || e.account_id === q.account_id || e.to_account_id === q.account_id)
    .filter((e) => !q.label_id || e.label_id === q.label_id)
    .filter((e) => !q.kind || e.kind === q.kind)
    .filter(
      (e) =>
        !needle ||
        (e.payee ?? '').toLowerCase().includes(needle) ||
        (e.note ?? '').toLowerCase().includes(needle),
    )
    .sort(byDateDesc);
}

/**
 * GET /entries: `{entries, next_cursor, totals}`. Totals cover the FULL filtered set
 * (voids excluded — they are not in `live()`); the cursor is `date|id` of the last row and
 * `limit` defaults to 100, max 500 (422 above, as pydantic would).
 */
export function pfListEntries(q: EntryFilter): EntriesPage {
  const limit = q.limit ?? 100;
  if (!Number.isInteger(limit) || limit < 1) {
    throw pydanticError(['query', 'limit'], 'Input should be greater than or equal to 1', 'greater_than_equal');
  }
  if (limit > 500) {
    throw pydanticError(['query', 'limit'], 'Input should be less than or equal to 500', 'less_than_equal');
  }
  const all = filtered(q);
  let inn = 0n;
  let out = 0n;
  for (const e of all) {
    // Same convention as the server (aurum/pf/entries.py totals): `out` is Σ|amount|, positive.
    if (e.kind === 'income') inn += e.cents;
    else if (e.kind === 'expense') out += -e.cents;
  }
  let start = 0;
  if (q.cursor) {
    const [cDate, cId] = q.cursor.split('|');
    const i = all.findIndex((e) => e.date === cDate && e.id === cId);
    if (i < 0) throw detailError(400, 'invalid cursor');
    start = i + 1;
  }
  const page = all.slice(start, start + limit);
  const last = page[page.length - 1];
  const next_cursor = start + limit < all.length && last ? `${last.date}|${last.id}` : null;
  const currency = all[0]?.currency ?? CURRENCY;
  return {
    entries: page.map(publicEntry),
    next_cursor,
    totals: {
      in: money(fromCents(inn), currency),
      out: money(fromCents(out), currency),
      net: money(fromCents(inn - out), currency),
      count: all.length,
    },
  };
}

function validateEntry(body: Partial<EntryInput>, kind: EntryKind, accountId: string): void {
  if (body.amount) {
    if (!/^-?\d+(\.\d{1,2})?$/.test(body.amount.amount.trim())) {
      throw pydanticError(['body', 'amount', 'amount'], 'Input should be a valid decimal');
    }
    if (toCents(body.amount.amount) <= 0n) {
      throw pydanticError(['body', 'amount'], 'amount must be greater than 0', 'greater_than');
    }
    if (body.amount.currency && !/^[A-Z]{3}$/.test(body.amount.currency)) {
      throw pydanticError(['body', 'amount', 'currency'], 'String should match pattern ^[A-Z]{3}$');
    }
  }
  if (body.date !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(body.date)) {
    throw pydanticError(['body', 'date'], 'Input should be a valid date');
  }
  const acct = accounts.find((a) => a.id === accountId);
  if (!acct) throw detailError(404, `account ${accountId} not found`);
  if (acct.archived) throw detailError(400, `account ${accountId} is archived`);
  if (kind === 'transfer') {
    if (!body.to_account_id) throw detailError(400, 'transfer requires to_account_id');
    if (body.to_account_id === accountId) throw detailError(400, 'transfer cannot use the same account twice');
    const to = accounts.find((a) => a.id === body.to_account_id);
    if (!to) throw detailError(404, `account ${body.to_account_id} not found`);
    if (to.archived) throw detailError(400, `account ${body.to_account_id} is archived`);
  }
  if (body.tags?.some((t) => !/^[A-Za-z0-9_-]+$/.test(t))) throw detailError(400, 'invalid tag');
  if (body.splits && body.splits.length > 0 && body.amount) {
    const total = toCents(body.amount.amount.replace(/^-/, ''));
    const sum = body.splits.reduce((acc, s) => acc + toCents(s.amount.amount.replace(/^-/, '')), 0n);
    if (body.splits.some((s) => !s.label_id)) throw detailError(400, 'split rows need label_id');
    if (sum !== total) throw detailError(400, `splits must sum to ${body.amount.amount}, got ${fromCents(sum)}`);
  }
}

export function pfCreateEntry(body: EntryInput, source: EntrySource = 'manual'): Entry {
  if (!body?.account_id) throw pydanticError(['body', 'account_id'], 'Field required', 'missing');
  if (!body.amount) throw pydanticError(['body', 'amount'], 'Field required', 'missing');
  validateEntry(body, body.kind, body.account_id);
  const rec = seedEntry({
    date: body.date || TODAY_ISO,
    kind: body.kind,
    cents: signedCents(body.kind, body.amount.amount),
    currency: body.amount.currency || CURRENCY,
    account_id: body.account_id,
    to_account_id: body.kind === 'transfer' ? (body.to_account_id ?? null) : null,
    label_id: body.label_id ?? null,
    payee: body.payee ?? null,
    note: body.note ?? null,
    tags: body.tags ?? [],
    splits: body.splits ?? null,
    source,
    commitment_id: body.commitment_id ?? null,
  });
  entries.push(rec);
  return publicEntry(rec);
}

/** PUT — partial body, validate-then-write; a voided row answers 409, a locked one 403. */
export function pfUpdateEntry(id: string, body: Partial<EntryInput>): Entry {
  const i = entries.findIndex((e) => e.id === id);
  if (i < 0) throw detailError(404, `entry ${id} not found`);
  const prev = entries[i];
  if (prev.voided) throw detailError(409, `entry ${id} was deleted`);
  if (!prev.editable) throw detailError(403, prev.non_editable_reason ?? `entry ${id} is not editable`);
  const kind = body.kind ?? prev.kind;
  const accountId = body.account_id ?? prev.account_id;
  validateEntry({ ...body, to_account_id: body.to_account_id ?? prev.to_account_id }, kind, accountId);
  const amount = body.amount?.amount ?? fromCents(prev.cents);
  const next: EntryRec = {
    ...prev,
    date: body.date || prev.date,
    kind,
    cents: signedCents(kind, amount),
    currency: body.amount?.currency || prev.currency,
    account_id: accountId,
    to_account_id: kind === 'transfer' ? (body.to_account_id ?? prev.to_account_id) : null,
    label_id: body.label_id !== undefined ? body.label_id : prev.label_id,
    payee: body.payee !== undefined ? body.payee : prev.payee,
    note: body.note !== undefined ? body.note : prev.note,
    tags: body.tags ?? prev.tags,
    splits: body.splits !== undefined ? body.splits : prev.splits,
    commitment_id: body.commitment_id !== undefined ? body.commitment_id : prev.commitment_id,
    edited: true,
  };
  entries[i] = next;
  return publicEntry(next);
}

/** DELETE → void: the row stays, flagged; lists/totals/balances exclude it; twice → 409. */
export function pfDeleteEntry(id: string): { id: string; voided: true } {
  const rec = entries.find((e) => e.id === id);
  if (!rec) throw detailError(404, `entry ${id} not found`);
  if (rec.voided) throw detailError(409, `entry ${id} was already deleted`);
  rec.voided = true;
  return { id, voided: true };
}

/** All-or-nothing: validate every row first, then write. */
export function pfBulkEntries(list: EntryInput[], source: EntrySource = 'import'): { created: string[] } {
  list.forEach((b, index) => {
    try {
      if (!b?.account_id || !b.amount) throw new Error('account_id and amount are required');
      validateEntry(b, b.kind, b.account_id);
    } catch (e) {
      const msg = e instanceof MockHttpError ? JSON.stringify(e.body) : e instanceof Error ? e.message : String(e);
      throw new MockHttpError(400, { detail: { index, msg } });
    }
  });
  return { created: list.map((b) => pfCreateEntry(b, source).id) };
}

/** The entry a commitment occurrence maps to: the `commitment_id` link first, then payee ±3 d ±10 %. */
export function pfFindMatchingEntry(
  commitmentId: string,
  payee: string,
  due: string,
  amount: string,
): Entry | null {
  const linked = live().find((e) => e.commitment_id === commitmentId && Math.abs(daysBetween(e.date, due)) <= 3);
  if (linked) return publicEntry(linked);
  const words = payee.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
  const target = toCents(amount.replace(/^-/, ''));
  const tolerance = target / 10n;
  const hit = live().find((e) => {
    if (e.kind === 'transfer' || Math.abs(daysBetween(e.date, due)) > 3) return false;
    const hay = (e.payee ?? '').toLowerCase();
    if (!words.some((w) => new RegExp(`\\b${w}\\b`).test(hay))) return false;
    const abs = e.cents < 0n ? -e.cents : e.cents;
    return abs >= target - tolerance && abs <= target + tolerance;
  });
  return hit ? publicEntry(hit) : null;
}

/** True when the row was never edited after being auto-created (an un-mark may void it). */
export function pfEntryUntouched(id: string): boolean {
  const rec = entries.find((e) => e.id === id);
  return !!rec && !rec.edited && !rec.voided;
}

function daysBetween(a: string, b: string): number {
  const [ay, am, ad] = a.split('-').map(Number);
  const [by, bm, bd] = b.split('-').map(Number);
  return Math.round((Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / 86_400_000);
}

/** Σ expense entries per label inside a period — what the budget status calls `spent`. */
export function pfSpentByLabel(period: string): Record<string, bigint> {
  const out: Record<string, bigint> = {};
  for (const e of live()) {
    if (e.kind !== 'expense' || !e.date.startsWith(period)) continue;
    const parts = e.splits && e.splits.length > 0 ? e.splits.map((s) => [s.label_id, -toCents(s.amount.amount.replace(/^-/, ''))] as const) : [[e.label_id, e.cents] as const];
    for (const [label, cents] of parts) {
      if (!label) continue;
      out[label] = (out[label] ?? 0n) + -cents;
    }
  }
  return out;
}

/** True while any live entry references the label (DELETE /labels → 409). */
export const pfLabelInUse = (labelId: string) =>
  live().some((e) => e.label_id === labelId || e.splits?.some((s) => s.label_id === labelId));

/* ------------------------------------------------------- income streams */

export function pfListStreams(): IncomeStream[] {
  return streams.map((s) => ({ ...s, account_name: accountName(s.account_id) }));
}

export function pfCreateStream(body: IncomeStreamInput): IncomeStream {
  if (!body?.name?.trim()) throw pydanticError(['body', 'name'], 'String should have at least 1 character');
  if (body.account_id && !accounts.some((a) => a.id === body.account_id)) {
    throw detailError(404, `account ${body.account_id} not found`);
  }
  const s: IncomeStream = {
    id: nid('inc'),
    name: body.name,
    source_type: body.source_type ?? 'other',
    amount: body.amount,
    gross_amount: body.gross_amount ?? null,
    cadence: body.cadence ?? 'monthly',
    anchor_days: body.anchor_days ?? [],
    weekday: body.weekday ?? null,
    next_expected: body.next_expected || nextExpectedFor(body.cadence ?? 'monthly', body.anchor_days ?? []),
    account_id: body.account_id ?? null,
    label_id: body.label_id ?? null,
    active: body.active ?? true,
    notes: body.notes ?? null,
  };
  streams.push(s);
  return { ...s, account_name: accountName(s.account_id) };
}

/** PUT — partial merge in place (id kept); a bad account_id changes nothing (404). */
export function pfUpdateStream(id: string, body: Partial<IncomeStreamInput>): IncomeStream {
  const i = streams.findIndex((s) => s.id === id);
  if (i < 0) throw detailError(404, `stream ${id} not found`);
  if (body.account_id && !accounts.some((a) => a.id === body.account_id)) {
    throw detailError(404, `account ${body.account_id} not found`);
  }
  const prev = streams[i];
  const cadence = body.cadence ?? prev.cadence;
  const anchor = body.anchor_days ?? prev.anchor_days ?? [];
  const next: IncomeStream = {
    ...prev,
    ...body,
    id: prev.id,
    cadence,
    anchor_days: anchor,
    next_expected: body.next_expected ?? (body.cadence || body.anchor_days ? nextExpectedFor(cadence, anchor) : prev.next_expected),
  };
  streams[i] = next;
  return { ...next, account_name: accountName(next.account_id) };
}

export function pfDeleteStream(id: string): { ok: boolean } {
  const i = streams.findIndex((s) => s.id === id);
  if (i < 0) throw detailError(404, `stream ${id} not found`);
  streams.splice(i, 1);
  return { ok: true };
}

/**
 * GET /income/streams/{id}/history — the real shape (aurum/pf/streams.py): one row per
 * projected occurrence in the last ~3 months, matched to income entries by label/payee.
 */
export function pfStreamHistory(id: string): StreamHistoryRow[] {
  const s = streams.find((x) => x.id === id);
  if (!s) throw detailError(404, `stream ${id} not found`);
  const dues: string[] = [];
  const anchors = s.anchor_days && s.anchor_days.length ? s.anchor_days : [1];
  for (let back = 2; back >= 0; back -= 1) {
    const y = TODAY.getFullYear();
    const m = TODAY.getMonth() - back;
    const last = new Date(y, m + 1, 0).getDate();
    for (const d of anchors) {
      const due = localIso(new Date(y, m, Math.min(d, last)));
      if (due <= TODAY_ISO) dues.push(due);
    }
  }
  return dues.sort().map((due) => {
    const hit = live().find(
      (e) =>
        e.kind === 'income' &&
        Math.abs(daysBetween(e.date, due)) <= 3 &&
        ((s.label_id && e.label_id === s.label_id) || (e.payee ?? '').toLowerCase().includes(s.name.toLowerCase())),
    );
    const received = hit ? money(fromCents(hit.cents), hit.currency) : null;
    const status = hit ? (hit.date > due ? 'late' : 'received') : daysBetween(due, TODAY_ISO) > 3 ? 'missed' : 'pending';
    return { due, expected: s.amount, received, status, period: due.slice(0, 7) };
  });
}

/* ---------------------------------------------------------- onboarding */

/** `accounts, income, recurring, first_entries`; done = accounts && first_entries. */
export function pfOnboarding(recurringCount: number): Onboarding {
  const acc = accounts.filter((a) => !a.archived).length;
  const first = live().filter((e) => e.source === 'manual' || e.source === 'quickadd').length;
  const steps: Onboarding['steps'] = [
    { id: 'accounts', done: acc > 0, count: acc, hint: null },
    { id: 'income', done: streams.length > 0, count: streams.length, hint: null },
    { id: 'recurring', done: recurringCount > 0, count: recurringCount, hint: null },
    { id: 'first_entries', done: first > 0, count: first, hint: null },
  ];
  return { steps, done: steps[0].done && steps[3].done };
}

/** Used by index.ts to fill `label_name` from the live label list it owns. */
export const PF5 = { accounts, entries, streams };
