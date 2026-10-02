/**
 * In-browser fake API (`NEXT_PUBLIC_MOCK=1`, i.e. `npm run dev:mock` / `build:mock`).
 *
 * Patches `window.fetch` and answers every endpoint from ./fixtures, matching the REAL
 * response shapes captured in `web-ui/docs/api-samples.json` — most list endpoints return a
 * bare array, not an envelope. It keeps a little state so the app is exercisable without a
 * backend: quick-add really parses a line into a proposed posting, accepting an inbox item
 * really removes it from the queue and lands in the journal, and the loan amortization is
 * really computed.
 *
 * Money discipline holds here too: every amount is produced as a decimal *string*. The
 * amortization generator works in integer centavos (BigInt), which is the mock's stand-in
 * for the API's Decimal — no binary float ever produces a figure the UI displays.
 *
 * Loaded by a dynamic import from lib/api.ts, so it is a separate chunk that a production
 * build never pulls in.
 */
import { API_BASE } from '../api';
import type {
  Amortization,
  CreditReportImport,
  CrossborderProfile,
  HoldingsOverview,
  SavedScenario,
  AmortRow,
  Amount,
  Budget,
  CFDI,
  CreditCard,
  CreditScore,
  Goal,
  InboxItem,
  Label,
  Loan,
  MonthClose,
  ReconcileBankLine,
  ResearchAnswer,
  Statement,
  StatementSection,
  StatementType,
  Transaction,
  WorkflowRun,
  WorkflowRunStep,
  WorkflowRunSummary,
  Workspace,
} from '../types';
import {
  ACCOUNTS,
  ACCOUNTS_OVERVIEW,
  BALANCES,
  BQL_ROWS,
  BUDGETS,
  CARDS,
  CFDIS,
  CHANGES,
  DEMO_PERIOD,
  GOAL_PROJECTIONS,
  GOALS,
  HEALTH,
  INBOX_SEED,
  INCOME,
  JOBS,
  JOURNAL,
  LABELS,
  LOANS,
  MONTH_CLOSE,
  PERSONAL_WS_ID,
  RECURRING,
  RESEARCH_ABSTAIN,
  RESEARCH_ANSWERS,
  REVIEW,
  RULES,
  VAULT,
  WORKSPACES,
  WS_ID,
} from './fixtures';
import {
  ARCHIVE_SEED,
  BIZ_CONSTANTS,
  BIZ_WORKSPACE,
  EMPLOYEES,
  INVOICE_REGISTER,
  PAYROLL_RUNS,
  PROPOSED_YAML,
  WORKFLOWS_SEED,
  WORKFLOW_CATALOG,
  bizKpis,
  calendarFor,
  digestFor,
  insightsFor,
  payrollRun,
  reportCatalog,
  reportHtml,
  reportPreview,
} from './fixtures-business';
import type { WorkflowSeed } from './fixtures-business';
import {
  MockHttpError,
  PF5,
  currentPeriodLocal,
  fromCents as fromCents5,
  pfAdjustAccount,
  pfBulkEntries,
  pfCreateAccount,
  pfCreateEntry,
  pfCreateStream,
  pfDeleteAccount,
  pfDeleteEntry,
  pfDeleteStream,
  pfGetAccount,
  pfLabelInUse,
  pfListAccounts,
  pfListEntries,
  pfListStreams,
  pfNetWorth,
  pfOnboarding,
  pfSpentByLabel,
  pfStreamHistory,
  pfUpdateAccount,
  pfUpdateEntry,
  pfUpdateStream,
  pydanticError,
  toCents as toCents5,
  todayLocalIso,
} from './fixtures-personal';
import {
  ORG,
  orgAcceptCandidate,
  orgAlerts,
  orgAutoPlan,
  orgCalendar,
  orgCreate,
  orgDetail,
  orgDetect,
  orgDismissCandidate,
  orgForecast,
  orgList,
  orgMark,
  orgMarkBody,
  orgOrganize,
  orgPlan,
  orgPutPlan,
  orgQuickAdd,
  orgSetStatus,
  orgSetupRun,
  orgSetupStatus,
  orgSummary,
  orgUnmark,
  orgUpdate,
} from './fixtures-organizer';
import {
  CREDIT_EXPLAIN,
  CREDIT_IMPORTS,
  REFS,
  SCENARIO_RESULTS,
  SCENARIOS,
  TX_FRANCHISE,
  US_TAX,
  US_WS_ID,
  WATCH_HISTORY,
  WATCH_PROPOSALS,
  WATCH_SOURCES,
  XB_PROFILE,
  holdingsSeed,
  xbAssessment,
} from './fixtures-tax';

/* ------------------------------------------------------------------- state */

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

const state = {
  inbox: clone(INBOX_SEED) as InboxItem[],
  journal: clone(JOURNAL) as Transaction[],
  cfdis: clone(CFDIS) as CFDI[],
  // Everything the write forms can change lives here, so `build:mock` demos really persist
  // for the life of the page: create, edit and delete all mutate these arrays and the next
  // GET reads them back, exactly as the app does against the real API.
  workspaces: clone([...WORKSPACES, BIZ_WORKSPACE]) as Workspace[],
  goals: clone(GOALS) as Goal[],
  budgets: seedBudgets(),
  labels: clone(LABELS) as Label[],
  cards: clone(CARDS) as CreditCard[],
  loans: clone(LOANS) as Loan[],
  scores: [] as CreditScore[],
  /** bank_line_id -> what it was matched to. */
  matches: {} as Record<string, { txn_id?: string; cfdi_uuid?: string }>,
  seq: 100,
};

const nextId = (prefix: string) => `${prefix}-${(state.seq += 1)}`;

/**
 * Budget fixture: the fixture budgets are re-dated to the month before the CURRENT local one
 * (all of them) and to the current month (all but one), so 'Copiar del mes anterior' has one
 * row to create and the rest to skip, and `has_previous` is true.
 */
function seedBudgets(): Budget[] {
  const period = currentPeriodLocal();
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1;
  const prevDate = new Date(Date.UTC(y, m - 1, 1));
  const prev = `${prevDate.getUTCFullYear()}-${String(prevDate.getUTCMonth() + 1).padStart(2, '0')}`;
  const base = clone(BUDGETS) as Budget[];
  const extra: Budget = { id: 'bud-rent', ws_id: WS_ID, label_id: 'lbl-d92e338efc65', period: prev, amount: '12500', currency: 'MXN', rollover: false };
  return [
    ...base.map((b) => ({ ...b, id: `${b.id}-prev`, period: prev })),
    extra,
    ...base.map((b) => ({ ...b, period })),
  ];
}

/* ------------------------------------------------------- decimal helpers */

/** "1234.56" → 123456n centavos. Exact: string arithmetic only. */
function toCents(decimal: string): bigint {
  const neg = decimal.trim().startsWith('-');
  const [int = '0', frac = ''] = decimal.trim().replace(/^[+-]/, '').split('.');
  const cents = BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2));
  return neg ? -cents : cents;
}

function fromCents(cents: bigint): string {
  const neg = cents < 0n;
  const abs = neg ? -cents : cents;
  const int = abs / 100n;
  const frac = (abs % 100n).toString().padStart(2, '0');
  return `${neg ? '-' : ''}${int}.${frac}`;
}

/** Monthly rate as a fraction of 1e10, so interest stays integer arithmetic. */
const RATE_SCALE = 10_000_000_000n;

function monthlyRateScaled(annualRate: string): bigint {
  const [int = '0', frac = ''] = annualRate.split('.');
  const scaled = BigInt(int) * RATE_SCALE + BigInt((frac + '0'.repeat(10)).slice(0, 10));
  return scaled / 12n;
}

/**
 * Amortization from the loan's stated principal/rate/months, plus an optional extra monthly
 * payment. Interest = balance × monthly rate, rounded half-up to the centavo, exactly as the
 * Python side would with Decimal. `payment` is solved via the standard annuity formula.
 */
function computeBasePayment(principalCents: bigint, rate: bigint, months: number): bigint {
  // pmt = P * r / (1 - (1+r)^-n), all done in floating approx then reconciled to cents,
  // acceptable for a mock (never used for real tax/ledger figures).
  const p = Number(principalCents) / 100;
  const r = Number(rate) / Number(RATE_SCALE);
  const pmt = r === 0 ? p / months : (p * r) / (1 - Math.pow(1 + r, -months));
  return BigInt(Math.round(pmt * 100));
}

function amortize(loanId: string, extra: string | null): Amortization {
  const loan = LOANS.find((l) => l.id === loanId) ?? LOANS[0];
  const rate = monthlyRateScaled(loan.annual_rate);
  const principalCents = toCents(loan.principal);
  const basePayment = computeBasePayment(principalCents, rate, loan.months);
  const extraCents = extra ? toCents(extra) : 0n;
  const payment = basePayment + extraCents;

  let balance = principalCents;
  let totalInterest = 0n;
  let totalPaid = 0n;
  const rows: AmortRow[] = [];
  for (let n = 1; n <= 600 && balance > 0n; n += 1) {
    const raw = balance * rate;
    const interest = (raw + RATE_SCALE / 2n) / RATE_SCALE;
    let principal = payment - interest;
    if (principal <= 0n) break;
    if (principal > balance) principal = balance;
    const paid = principal + interest;
    balance -= principal;
    totalInterest += interest;
    totalPaid += paid;
    rows.push({
      month: n,
      payment: fromCents(paid),
      interest: fromCents(interest),
      principal: fromCents(principal),
      balance: fromCents(balance),
    });
  }

  return {
    loan_id: loan.id,
    payment: fromCents(basePayment),
    total_paid: fromCents(totalPaid),
    total_interest: fromCents(totalInterest),
    rows,
    explain: {
      summary: extraCents
        ? `Con un pago extra de $${fromCents(extraCents)} al mes el préstamo se liquida en ${rows.length} pagos y el interés total baja a $${fromCents(totalInterest)}.`
        : `${rows.length} pagos de $${fromCents(basePayment)}; el interés total es $${fromCents(totalInterest)}.`,
      steps: [
        { label: 'Capital', formula: null, value: loan.principal },
        { label: 'Pago', formula: null, value: fromCents(basePayment) },
        { label: 'Interés total', formula: 'suma de saldo × tasa mensual', value: fromCents(totalInterest) },
      ],
      citations: [],
      rule_versions: ['pf.finance.buildAmortization@2026.1'],
      confidence: 0.99,
    },
  };
}

/* ------------------------------------------------------------- quick add */

const LABEL_KEYWORDS: { re: RegExp; label: string; account: string }[] = [
  { re: /taco|comida|restaurant|cena|desayuno|almuerzo|food|lunch/i, label: 'comida', account: 'Expenses:Food:DiningOut' },
  { re: /uber|didi|taxi|gasolina|gas|transporte|camion/i, label: 'transporte', account: 'Expenses:Transport' },
  { re: /software|suscrip|saas|licencia|subscription/i, label: 'software', account: 'Expenses:Software' },
  { re: /renta|oficina|papeler|office|rent/i, label: 'oficina', account: 'Expenses:Office' },
  { re: /internet|telefon|luz|agua|cfe|servicio/i, label: 'servicios', account: 'Expenses:Utilities' },
];

/** Rule-based first, as the real ingest does; no model involved in the mock. */
function parseQuickAdd(text: string): InboxItem {
  const amountMatch = text.match(/(\d[\d,]*(?:\.\d{1,2})?)/);
  const rawAmount = amountMatch ? amountMatch[1].replace(/,/g, '') : '0';
  const amount = rawAmount.includes('.') ? Number(rawAmount).toFixed(2) : `${rawAmount}.00`;
  const rest = text.replace(amountMatch?.[0] ?? '', '').trim();
  const hit = LABEL_KEYWORDS.find((k) => k.re.test(text));
  const words = rest.split(/\s+/).filter(Boolean);
  const payee = words.length ? words[0].replace(/^./, (c) => c.toUpperCase()) : null;
  const today = todayLocalIso();

  return {
    id: nextId('inbox'),
    ws_id: WS_ID,
    kind: 'quickadd',
    status: 'pending',
    proposed: {
      date: today,
      payee,
      narration: text,
      postings: [
        { account: 'Assets:Cash', amount: { amount: `-${amount}`, currency: 'MXN' } },
        { account: hit?.account ?? 'Expenses:Uncategorized', amount: null },
      ],
      tags: [],
      links: [],
      meta: { source: 'quickadd', raw_text: text, ...(hit ? { label: hit.label } : {}) },
    },
    confidence: hit ? (payee ? 0.86 : 0.72) : 0.45,
    source_ref: null,
    created_at: `${today}T12:00:00Z`,
    decided_at: null,
    warnings: [],
  };
}

/* ------------------------------------------------------------------ routes */

type Handler = (ctx: {
  m: RegExpMatchArray;
  url: URL;
  body: unknown;
  init: RequestInit | undefined;
}) => unknown;

interface Route {
  method: string;
  pattern: RegExp;
  handler: Handler;
}

const R: Route[] = [];
const route = (method: string, pattern: RegExp, handler: Handler) => R.push({ method, pattern, handler });

/* core */
route('GET', /^\/health$/, () => HEALTH);
const isDemoWs = (w: Workspace) => w.profile?.demo === true;
/** Personal non-demo first (created_at), then other non-demo, then demos; hidden omitted. */
route('GET', /^\/workspaces$/, ({ url }) => {
  const includeHidden = url.searchParams.get('include_hidden') === '1';
  const rank = (w: Workspace) => (w.kind === 'personal' && !isDemoWs(w) ? 0 : !isDemoWs(w) ? 1 : 2);
  return state.workspaces
    .filter((w) => includeHidden || !w.hidden)
    .slice()
    .sort((a, b) => rank(a) - rank(b) || (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0));
});
route('GET', /^\/workspaces\/([^/]+)$/, ({ m }) => state.workspaces.find((w) => w.id === m[1]) ?? state.workspaces[0]);

/* ledger */
route('GET', /^\/ledger\/([^/]+)\/journal$/, ({ url }) => {
  const start = url.searchParams.get('start');
  const end = url.searchParams.get('end');
  const prefix = url.searchParams.get('account_prefix');
  return state.journal
    .filter((t) => (!start || t.date >= start) && (!end || t.date <= end))
    .filter((t) => !prefix || t.postings.some((p) => p.account.startsWith(prefix)))
    .sort((a, b) => (a.date < b.date ? 1 : -1));
});
route('GET', /^\/ledger\/([^/]+)\/balances$/, () => BALANCES);
route('GET', /^\/ledger\/([^/]+)\/accounts$/, () => ACCOUNTS);
route('POST', /^\/ledger\/([^/]+)\/query$/, ({ body }) => {
  const bql = String((body as { bql?: string })?.bql ?? '');
  if (!/select/i.test(bql)) {
    throw new HttpError(400, 'La consulta debe empezar con SELECT (beanquery).');
  }
  return BQL_ROWS;
});

/* rules */
route('GET', /^\/rules$/, () => RULES);
route('POST', /^\/rules\/([^/]+)\/compute$/, ({ m }) => {
  const close = MONTH_CLOSE[DEMO_PERIOD];
  if (m[1] === 'mx.iva.monthly') return { value: close.iva.payable, explain: close.iva.explain };
  return { value: close.isr.value, explain: close.isr.explain };
});

/* tax */
route('GET', /^\/tax\/mx\/resico\/([^/]+)\/(\d{4}-\d{2})$/, ({ m }) => {
  const close: MonthClose | undefined = MONTH_CLOSE[m[2]];
  if (!close) throw new HttpError(404, `No hay cierre para el periodo ${m[2]} en el espacio de demostración.`);
  return close;
});

/* ingest */
route('GET', /^\/ingest\/([^/]+)\/cfdi$/, ({ url }) => {
  const period = url.searchParams.get('period');
  const tipo = url.searchParams.get('tipo');
  const metodo = url.searchParams.get('metodo_pago');
  const direction = url.searchParams.get('direction');
  return state.cfdis.filter(
    (c) =>
      (!period || c.fecha.startsWith(period)) &&
      (!tipo || c.tipo === tipo) &&
      (!metodo || c.metodo_pago === metodo) &&
      (!direction || c.direction === direction),
  );
});
route('POST', /^\/ingest\/([^/]+)\/cfdi$/, ({ init }) => {
  const form = init?.body as FormData;
  const files = form ? form.getAll('files') : [];
  return {
    accepted: files.length,
    inbox_items: files.map(() => nextId('inbox')),
    warnings: files.length ? [] : ['No se recibió ningún archivo.'],
  };
});
/** `account_id` is required; rows land as pf entries (source import, deduplicated). */
route('POST', /^\/ingest\/([^/]+)\/bank\/csv$/, ({ init }) => {
  const form = init?.body as FormData;
  const accountId = form ? String(form.get('account_id') ?? '') : '';
  if (!accountId) throw pydanticError(['body', 'account_id'], 'Field required', 'missing');
  const acct = pfGetAccount(accountId);
  if (!acct) throw new HttpError(404, `account ${accountId} not found`);
  const bank = form ? String(form.get('bank') ?? '') : '';
  const today = todayLocalIso();
  const rows = [
    { date: today, amount: '-489.00', payee: 'OXXO' },
    { date: today, amount: '-1200.00', payee: 'CFE' },
  ];
  const created = pfBulkEntries(
    rows.map((r) => ({
      kind: 'expense' as const,
      date: r.date,
      amount: { amount: r.amount.replace(/^-/, ''), currency: acct.currency ?? 'MXN' },
      account_id: accountId,
      payee: r.payee,
      tags: ['import', ...(bank ? [`csv-${bank.toLowerCase()}`] : [])],
    })),
    'import',
  );
  return { created: created.created, skipped_duplicates: 0, errors: [] };
});
/**
 * A parsed preview (`preview/confidence/warnings`), never an inbox row; `commit: true`
 * writes the pf entry (source quickadd). The legacy inbox fields ride along for older
 * callers.
 */
route('POST', /^\/ingest\/([^/]+)\/quickadd$/, ({ body }) => {
  const text = String((body as { text?: string })?.text ?? '').trim();
  if (!text) throw pydanticError(['body', 'text'], 'String should have at least 1 character');
  const r = asRecord(body);
  const accountId = typeof r.account_id === 'string' && r.account_id ? r.account_id : null;
  const live = PF5.accounts.filter((a) => !a.archived);
  const acct =
    (accountId ? pfGetAccount(accountId) : null) ??
    live.find((a) => new RegExp(`\\b${a.name.split(/\s+/)[0]}\\b`, 'i').test(text)) ??
    (live.filter((a) => a.type === 'cash' || a.type === 'checking').length === 1
      ? live.find((a) => a.type === 'cash' || a.type === 'checking')
      : null) ??
    null;
  if (accountId && !acct) throw new HttpError(404, `account ${accountId} not found`);
  if (!acct) throw new HttpError(400, 'Primero agrega una cuenta');
  const item = parseQuickAdd(text);
  const amount = item.proposed.postings[0].amount?.amount.replace(/^-/, '') ?? '0.00';
  const hit = state.labels.find((l) => (l.kind ?? 'expense') === 'expense' && l.aliases.some((a) => new RegExp(`\\b${a}\\b`, 'i').test(text)));
  const preview = {
    kind: 'expense' as const,
    amount: { amount, currency: acct.currency ?? 'MXN' },
    account_id: acct.id,
    account_name: acct.name,
    label_id: hit?.id ?? null,
    label_name: hit?.name ?? null,
    payee: item.proposed.payee ?? null,
    date: todayLocalIso(),
  };
  const warnings: string[] = [];
  if (!hit) warnings.push('Sin categoría: elige una antes de guardar.');
  if (amount === '0.00') warnings.push('No encontré un monto en el texto.');
  const entry = r.commit === true
    ? withLabelNames([
        pfCreateEntry(
          { kind: 'expense', date: preview.date, amount: preview.amount, account_id: acct.id, label_id: preview.label_id, payee: preview.payee },
          'quickadd',
        ),
      ])[0]
    : null;
  return { ...item, preview, confidence: hit ? 0.86 : 0.55, warnings, entry };
});
route('GET', /^\/ingest\/([^/]+)\/inbox$/, ({ url }) => {
  const status = url.searchParams.get('status');
  return state.inbox.filter((i) => !status || i.status === status);
});
route('POST', /^\/ingest\/([^/]+)\/inbox\/([^/]+)\/accept$/, ({ m, body }) => {
  const item = state.inbox.find((i) => i.id === m[2]);
  if (!item) throw new HttpError(404, 'La partida ya no está en la bandeja.');
  const overrides = (body ?? {}) as { label?: string; account?: string };
  const accepted: InboxItem = {
    ...item,
    status: 'accepted',
    decided_at: new Date().toISOString(),
    proposed: {
      ...item.proposed,
      meta: { ...item.proposed.meta, ...(overrides.label ? { label: overrides.label } : {}) },
      postings: overrides.account
        ? item.proposed.postings.map((p, i) => (i === 1 ? { ...p, account: overrides.account! } : p))
        : item.proposed.postings,
    },
  };
  state.inbox = state.inbox.filter((i) => i.id !== item.id);
  state.journal = [accepted.proposed, ...state.journal];
  return accepted;
});
route('POST', /^\/ingest\/([^/]+)\/inbox\/([^/]+)\/reject$/, ({ m }) => {
  const item = state.inbox.find((i) => i.id === m[2]);
  if (!item) throw new HttpError(404, 'La partida ya no está en la bandeja.');
  state.inbox = state.inbox.filter((i) => i.id !== item.id);
  return { ...item, status: 'rejected' as const, decided_at: new Date().toISOString() };
});

/* satsync */
route('GET', /^\/satsync\/([^/]+)\/vault$/, () => VAULT);
route('GET', /^\/satsync\/([^/]+)\/jobs$/, () => JOBS);

/* pf */
/**
 * The original overview shape is preserved and the friendly `accounts` rows are
 * added alongside it, which is what the personal screens read.
 */
route('GET', /^\/pf\/([^/]+)\/accounts$/, ({ url }) => ({
  ...ACCOUNTS_OVERVIEW,
  // ΣAssets + ΣLiabilities, signed, from the pf accounts the person actually has.
  net_worth: pfNetWorth(),
  accounts: pfListAccounts(url.searchParams.get('include_archived') === '1'),
}));
route('GET', /^\/pf\/([^/]+)\/income$/, () => INCOME);
/** `?kind=expense|income`, archived hidden unless `include_archived=1`. */
route('GET', /^\/pf\/([^/]+)\/labels$/, ({ url }) => {
  const kind = url.searchParams.get('kind');
  const includeArchived = url.searchParams.get('include_archived') === '1';
  return state.labels
    .filter((l) => !kind || (l.kind ?? 'expense') === kind)
    .filter((l) => includeArchived || !l.archived);
});
route('GET', /^\/pf\/([^/]+)\/budgets$/, ({ url }) => {
  const period = url.searchParams.get('period');
  return state.budgets.filter((b) => !period || b.period === period);
});
/** Budget status shape, computed live from the budget rows and the pf entries of the period. */
route('GET', /^\/pf\/([^/]+)\/budgets\/status$/, ({ url }) => budgetStatus(url.searchParams.get('period')));
route('GET', /^\/pf\/([^/]+)\/goals$/, () => state.goals.map(withGoalAccount));
route('GET', /^\/pf\/([^/]+)\/goals\/([^/]+)\/projection$/, ({ m }) => {
  const path = GOAL_PROJECTIONS[m[2]] ?? [];
  return {
    goal_id: m[2],
    path,
    explain: {
      summary: 'Projection assumes a constant monthly contribution equal to monthly_required.',
      steps: [],
      citations: [],
      rule_versions: [],
      confidence: null,
    },
  };
});
route('GET', /^\/pf\/([^/]+)\/credit\/cards$/, () => state.cards);
route('GET', /^\/pf\/([^/]+)\/credit\/loans$/, () => state.loans);
route('GET', /^\/pf\/([^/]+)\/credit\/loans\/([^/]+)\/amortization$/, ({ m, url }) =>
  amortize(m[2], url.searchParams.get('extra')),
);
route('POST', /^\/pf\/([^/]+)\/credit\/loans\/([^/]+)\/whatif$/, ({ m, body }) => {
  const extra = String((body as { extra_payment?: string })?.extra_payment ?? '0');
  const base = amortize(m[2], null);
  const withExtra = amortize(m[2], extra);
  const interestSaved = fromCentsDiff(base.total_interest, withExtra.total_interest);
  return {
    loan_id: m[2],
    months_to_payoff: withExtra.rows.length,
    months_saved: base.rows.length - withExtra.rows.length,
    new_total_interest: withExtra.total_interest,
    interest_saved: { amount: interestSaved, currency: 'MXN' },
    explain: {
      summary: 'Extra monthly payment shortens payoff and lowers total interest paid.',
      steps: [
        { label: 'base_months', formula: null, value: String(base.rows.length) },
        { label: 'new_months', formula: null, value: String(withExtra.rows.length) },
        { label: 'interest_saved', formula: null, value: interestSaved },
      ],
      citations: [],
      rule_versions: [],
      confidence: null,
    },
  };
});
route('GET', /^\/pf\/([^/]+)\/review\/(\d{4}-\d{2})$/, ({ m }) => {
  const r = REVIEW[m[2]];
  if (r) return r;
  // The server (aurum/pf/review.py monthly_review) answers 200 with zeros for a month without
  // movements, never 404 — the mock does the same so Home renders in any month.
  const base = REVIEW[DEMO_PERIOD];
  const zero = { amount: '0.00', currency: base.income.currency };
  return {
    ...base,
    period: m[2],
    income: zero,
    expense: zero,
    net: zero,
    vs_previous_month: { income_delta: '0.00', expense_delta: '0.00' },
    top_labels: [],
    anomalies: [],
    upcoming_bills: [],
    interest_paid: zero,
  };
});
route('GET', /^\/pf\/([^/]+)\/recurring$/, () => RECURRING);

function fromCentsDiff(a: string, b: string): string {
  const toC = (s: string) => {
    const neg = s.trim().startsWith('-');
    const [int = '0', frac = ''] = s.trim().replace(/^[+-]/, '').split('.');
    const c = BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2));
    return neg ? -c : c;
  };
  const diff = toC(a) - toC(b);
  const neg = diff < 0n;
  const abs = neg ? -diff : diff;
  return `${neg ? '-' : ''}${abs / 100n}.${(abs % 100n).toString().padStart(2, '0')}`;
}

/* research + watch — not yet checked against a real API response */
route('POST', /^\/research\/ask$/, ({ body }) => {
  const q = String((body as { question?: string })?.question ?? '');
  const hit = RESEARCH_ANSWERS.find((a) => a.match.test(q));
  const answer: ResearchAnswer = hit ? hit.answer : RESEARCH_ABSTAIN;
  return answer;
});
route('GET', /^\/watch\/changes$/, ({ url }) => {
  const since = url.searchParams.get('since');
  // The live API returns a bare array of change rows.
  return CHANGES.changes.filter((c) => !since || c.detected_at >= since);
});
route('POST', /^\/watch\/run$/, () => CHANGES);


/* ------------------------------------------------------------------ writes */
/**
 * Every write the UI can make, answered from `state`. Amounts stay decimal
 * *strings* end to end; the only arithmetic here is exact integer-centavo arithmetic, which is
 * the mock's stand-in for the API's `Decimal`.
 */

const amt = (amount: string, currency = 'MXN'): Amount => ({ amount, currency });
const plainExplain = (summary: string, steps: { label: string; value: string }[] = []) => ({
  summary,
  steps: steps.map((x) => ({ label: x.label, formula: null, value: x.value })),
  citations: [],
  rule_versions: [],
  confidence: null,
});

/** `{period, currency, budgets:[row], totals, has_previous, previous_period, safe_to_spend, explain}`. */
function budgetStatus(periodParam: string | null) {
  const period = periodParam ?? currentPeriodLocal();
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) {
    throw new MockHttpError(422, {
      detail: [{ loc: ['query', 'period'], msg: 'String should match pattern ^\\d{4}-(0[1-9]|1[0-2])$', type: 'string_pattern_mismatch' }],
    });
  }
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1;
  const prevDate = new Date(Date.UTC(y, m - 1, 1));
  const previous = `${prevDate.getUTCFullYear()}-${String(prevDate.getUTCMonth() + 1).padStart(2, '0')}`;
  const spent = pfSpentByLabel(period);
  let tBudget = 0n;
  let tSpent = 0n;
  let tRemaining = 0n;
  const rows = state.budgets
    .filter((b) => b.period === period)
    .map((b) => {
      const label = state.labels.find((l) => l.id === b.label_id);
      const budget = toCents5(b.amount);
      const carried = 0n;
      const effective = budget + carried;
      const sp = spent[b.label_id] ?? 0n;
      const remaining = effective - sp;
      tBudget += effective;
      tSpent += sp;
      tRemaining += remaining > 0n ? remaining : 0n;
      const pct = effective > 0n ? Number((sp * 1000n) / effective) / 10 : 0;
      const state_ = pct >= 100 ? 'over' : pct >= 80 ? 'warn' : 'ok';
      return {
        budget_id: b.id,
        label_id: b.label_id,
        label_name: label?.name ?? b.label_id,
        icon: label?.icon ?? null,
        budget: amt(fromCents5(budget), b.currency),
        carried: amt(fromCents5(carried), b.currency),
        effective: amt(fromCents5(effective), b.currency),
        spent: amt(fromCents5(sp), b.currency),
        remaining: amt(fromCents5(remaining), b.currency),
        pct,
        state: state_ as 'ok' | 'warn' | 'over',
        rollover: b.rollover,
      };
    });
  return {
    period,
    currency: 'MXN',
    budgets: rows,
    totals: { budget: amt(fromCents5(tBudget)), spent: amt(fromCents5(tSpent)), remaining: amt(fromCents5(tRemaining)) },
    has_previous: state.budgets.some((b) => b.period === previous),
    previous_period: state.budgets.some((b) => b.period === previous) ? previous : null,
    safe_to_spend: amt(fromCents5(tRemaining)),
    explain: plainExplain('Presupuesto restante: lo presupuestado menos lo gastado en cada categoría este mes.', [
      { label: 'Presupuestado', value: fromCents5(tBudget) },
      { label: 'Gastado', value: fromCents5(tSpent) },
      { label: 'Presupuesto restante', value: fromCents5(tRemaining) },
    ]),
  };
}

/** Feeds `budgets_remaining` into the organizer's safe_to_spend (index.ts owns budgets). */
ORG.budgetsRemaining = () => toCents5(budgetStatus(null).safe_to_spend.amount);

/** Goals carry the pf account they are funded from; `account` is derived. */
function withGoalAccount(g: Goal): Goal {
  const acct = g.account_id ? pfGetAccount(g.account_id) : PF5.accounts.find((a) => a.ledger_account === g.account) ?? null;
  const target = toCents5(g.target);
  const progress = toCents5(g.progress.amount);
  const pct = target > 0n ? Number((progress * 1000n) / target) / 10 : 0;
  return {
    ...g,
    account: acct?.ledger_account ?? g.account,
    account_id: acct?.id ?? null,
    account_name: acct?.name ?? null,
    pct,
  };
}

const asRecord = (body: unknown) => (body ?? {}) as Record<string, unknown>;
const str = (body: unknown, key: string, fallback = '') => {
  const v = asRecord(body)[key];
  return typeof v === 'string' ? v : fallback;
};
const num = (body: unknown, key: string, fallback = 0) => {
  const v = asRecord(body)[key];
  return typeof v === 'number' ? v : fallback;
};

/** The next day-of-month occurrence, as an ISO date — mirrors `credit._next_day`. */
function nextDay(day: number): string {
  const now = new Date();
  const candidate = new Date(now.getFullYear(), now.getMonth(), day);
  const target = candidate >= now ? candidate : new Date(now.getFullYear(), now.getMonth() + 1, day);
  return `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(
    target.getDate(),
  ).padStart(2, '0')}`;
}

/* workspaces */
route('POST', /^\/workspaces$/, ({ body }) => {
  const w = body as Workspace;
  if (!w?.id) throw new HttpError(422, 'El identificador es obligatorio.');
  if (state.workspaces.some((x) => x.id === w.id)) throw new HttpError(409, `El espacio ${w.id} ya existe.`);
  const created: Workspace = {
    ...w,
    profile: maskProfile(w.profile ?? {}),
    created_at: new Date().toISOString(),
  };
  state.workspaces = [...state.workspaces, created];
  return created;
});
route('PUT', /^\/workspaces\/([^/]+)$/, ({ m, body }) => {
  const i = state.workspaces.findIndex((w) => w.id === m[1]);
  if (i < 0) throw new HttpError(404, `No existe el espacio ${m[1]}.`);
  const patch = asRecord(body);
  const prev = state.workspaces[i];
  if (prev.protected && patch.protected === false) {
    throw new HttpError(400, `workspace ${prev.id} is protected and cannot be unprotected`);
  }
  const profile = maskProfile({ ...prev.profile, ...((patch.profile as Record<string, string>) ?? {}) });
  const next: Workspace = {
    ...prev,
    ...(patch as Partial<Workspace>),
    id: prev.id,
    profile,
    protected: prev.protected ?? false,
    hidden: typeof patch.hidden === 'boolean' ? patch.hidden : (prev.hidden ?? false),
  };
  state.workspaces = state.workspaces.map((w, j) => (j === i ? next : w));
  return next;
});

/** RFC/CURP/SSN never leave the API unmasked (aurum/core/workspaces.py::masked). */
function maskProfile(profile: Record<string, unknown>): Record<string, string | number | boolean | null> {
  const out: Record<string, string | number | boolean | null> = {};
  for (const [k, v] of Object.entries(profile)) {
    if (['rfc', 'curp', 'ssn', 'ein'].includes(k) && typeof v === 'string' && v.length > 4) {
      out[k] = '*'.repeat(v.length - 4) + v.slice(-4);
    } else {
      out[k] = v as string | number | boolean | null;
    }
  }
  return out;
}

/* goals */
function goalFromBody(body: unknown, id: string): Goal {
  const r = asRecord(body);
  const rawTarget = r.target;
  const target = typeof rawTarget === 'string' ? rawTarget : str(rawTarget, 'amount', '0');
  const currency = (typeof rawTarget === 'object' && rawTarget && str(rawTarget, 'currency')) || str(body, 'currency', 'MXN');
  const kind = str(body, 'kind', 'savings');
  if (!['savings', 'emergency', 'debt', 'purchase'].includes(kind)) {
    throw new MockHttpError(422, { detail: [{ loc: ['body', 'kind'], msg: "Input should be 'savings', 'emergency', 'debt' or 'purchase'", type: 'enum' }] });
  }
  const targetDate = (r.target_date as string | null) ?? null;
  if (targetDate && targetDate < todayLocalIso()) {
    throw new MockHttpError(422, { detail: [{ loc: ['body', 'target_date'], msg: 'target_date must not be in the past', type: 'value_error' }] });
  }
  const accountId = typeof r.account_id === 'string' ? r.account_id : null;
  if (accountId && !pfGetAccount(accountId)) throw new HttpError(404, `account ${accountId} not found`);
  const acct = accountId ? pfGetAccount(accountId) : null;
  return withGoalAccount({
    id,
    ws_id: WS_ID,
    kind: (str(body, 'kind', 'savings') as Goal['kind']) ?? 'savings',
    name: str(body, 'name'),
    target,
    currency: acct?.currency ?? currency,
    target_date: targetDate,
    account: acct?.ledger_account ?? str(body, 'account'),
    account_id: acct?.id ?? null,
    created_at: new Date().toISOString(),
    progress: amt('0', acct?.currency ?? currency),
    remaining: amt(target, acct?.currency ?? currency),
    monthly_required: null,
    explain: plainExplain('Aportación mensual necesaria: lo que falta entre los meses que quedan hasta la fecha meta.', [
      { label: 'Meta', value: target },
    ]),
  });
}
route('POST', /^\/pf\/([^/]+)\/goals$/, ({ body }) => {
  if (!str(body, 'name')) throw new HttpError(422, 'El nombre es obligatorio.');
  const goal = goalFromBody(body, nextId('goal'));
  state.goals = [...state.goals, goal];
  return goal;
});
route('PUT', /^\/pf\/([^/]+)\/goals\/([^/]+)$/, ({ m, body }) => {
  const prev = state.goals.find((g) => g.id === m[2]);
  if (!prev) throw new HttpError(404, `No existe la meta ${m[2]}.`);
  const merged = { ...prev, ...asRecord(body), target: asRecord(body).target ?? prev.target, account_id: asRecord(body).account_id ?? prev.account_id };
  const next = { ...goalFromBody(merged, prev.id), created_at: prev.created_at, progress: prev.progress };
  state.goals = state.goals.map((g) => (g.id === prev.id ? next : g));
  return next;
});
route('DELETE', /^\/pf\/([^/]+)\/goals\/([^/]+)$/, ({ m }) => {
  if (!state.goals.some((g) => g.id === m[2])) throw new HttpError(404, `No existe la meta ${m[2]}.`);
  state.goals = state.goals.filter((g) => g.id !== m[2]);
  return { ok: true };
});
route('POST', /^\/pf\/([^/]+)\/goals\/([^/]+)\/whatif$/, ({ m, body }) => {
  const goal = state.goals.find((g) => g.id === m[2]);
  if (!goal) throw new HttpError(404, `No existe la meta ${m[2]}.`);
  const extra = str(body, 'extra_monthly', '0');
  return {
    goal_id: goal.id,
    months_to_payoff: 0,
    months_saved: 0,
    interest_saved: amt('0.00', goal.currency),
    explain: plainExplain(
      `Aportar ${extra} extra al mes acorta el plazo de la meta (el API real hace el cálculo).`,
      [{ label: 'extra_monthly', value: extra }],
    ),
  };
});

/* budgets */
function budgetFromBody(body: unknown, id: string): Budget {
  return {
    id,
    ws_id: WS_ID,
    label_id: str(body, 'label_id'),
    period: str(body, 'period'),
    amount: str(body, 'amount', '0'),
    currency: str(body, 'currency', 'MXN'),
    rollover: Boolean(asRecord(body).rollover),
  };
}
/** POST /budgets/copy {from,to} — idempotent, skips labels already budgeted in `to`. */
route('POST', /^\/pf\/([^/]+)\/budgets\/copy$/, ({ body }) => {
  const from = str(body, 'from');
  const to = str(body, 'to');
  for (const [k, v] of [['from', from], ['to', to]] as const) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(v)) {
      throw new MockHttpError(422, { detail: [{ loc: ['body', k], msg: 'String should match pattern ^\\d{4}-(0[1-9]|1[0-2])$', type: 'string_pattern_mismatch' }] });
    }
  }
  let created = 0;
  let skipped = 0;
  for (const src of state.budgets.filter((b) => b.period === from)) {
    if (state.budgets.some((b) => b.period === to && b.label_id === src.label_id)) {
      skipped += 1;
      continue;
    }
    state.budgets = [...state.budgets, { ...src, id: nextId('bud'), period: to }];
    created += 1;
  }
  return { created, skipped, period: to };
});
route('POST', /^\/pf\/([^/]+)\/budgets$/, ({ body }) => {
  if (!str(body, 'label_id')) throw pydanticError(['body', 'label_id'], 'Field required', 'missing');
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(str(body, 'period'))) throw pydanticError(['body', 'period'], 'Input should be a valid period YYYY-MM');
  if (state.budgets.some((b) => b.label_id === str(body, 'label_id') && b.period === str(body, 'period'))) {
    throw new HttpError(409, `budget for label ${str(body, 'label_id')} in ${str(body, 'period')} already exists`);
  }
  const b = budgetFromBody(body, nextId('bud'));
  state.budgets = [...state.budgets, b];
  return b;
});
route('PUT', /^\/pf\/([^/]+)\/budgets\/([^/]+)$/, ({ m, body }) => {
  if (!state.budgets.some((b) => b.id === m[2])) throw new HttpError(404, `No existe el presupuesto ${m[2]}.`);
  const b = budgetFromBody(body, m[2]);
  state.budgets = state.budgets.map((x) => (x.id === m[2] ? b : x));
  return b;
});
route('DELETE', /^\/pf\/([^/]+)\/budgets\/([^/]+)$/, ({ m }) => {
  if (!state.budgets.some((b) => b.id === m[2])) throw new HttpError(404, `No existe el presupuesto ${m[2]}.`);
  state.budgets = state.budgets.filter((b) => b.id !== m[2]);
  return { ok: true };
});

/* labels */
function labelSlug(name: string): string {
  return (
    name
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^A-Za-z0-9 ]/g, ' ')
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => w[0].toUpperCase() + w.slice(1))
      .join('') || 'Categoria'
  );
}
function labelFromBody(body: unknown, id: string): Label {
  const r = asRecord(body);
  const kind = (str(body, 'kind', 'expense') as Label['kind']) ?? 'expense';
  if (kind !== 'expense' && kind !== 'income') {
    throw new MockHttpError(422, { detail: [{ loc: ['body', 'kind'], msg: "Input should be 'expense' or 'income'", type: 'enum' }] });
  }
  const parentId = typeof r.parent === 'string' ? r.parent : null;
  const parent = parentId ? state.labels.find((l) => l.id === parentId) : null;
  if (parentId && !parent) throw new HttpError(404, `label ${parentId} not found`);
  let account = str(body, 'account');
  if (!account) {
    const root = parent ? parent.account : kind === 'income' ? 'Income' : 'Expenses';
    let candidate = `${root}:${labelSlug(str(body, 'name'))}`;
    if (state.labels.some((l) => l.account === candidate)) candidate = `${candidate}2`;
    account = candidate;
  }
  if (!/^(Assets|Liabilities|Equity|Income|Expenses)(:[A-Z][A-Za-z0-9-]*)+$/.test(account)) {
    throw new HttpError(400, `invalid account name ${account}`);
  }
  return {
    id,
    ws_id: WS_ID,
    name: str(body, 'name'),
    aliases: Array.isArray(r.aliases) ? (r.aliases as string[]) : [],
    account,
    icon: (r.icon as string | null) ?? null,
    tax: (r.tax as Label['tax']) ?? {},
    sort: num(body, 'sort', state.labels.length),
    kind,
    archived: false,
    parent: parentId,
  };
}
route('POST', /^\/pf\/([^/]+)\/labels$/, ({ body }) => {
  if (!str(body, 'name').trim()) throw pydanticError(['body', 'name'], 'String should have at least 1 character');
  const l = labelFromBody(body, nextId('lbl'));
  state.labels = [...state.labels, l];
  return l;
});
route('PUT', /^\/pf\/([^/]+)\/labels\/([^/]+)$/, ({ m, body }) => {
  const prev = state.labels.find((l) => l.id === m[2]);
  if (!prev) throw new HttpError(404, `label ${m[2]} not found`);
  const r = asRecord(body);
  const next: Label = {
    ...prev,
    name: typeof r.name === 'string' && r.name.trim() ? r.name : prev.name,
    icon: r.icon !== undefined ? (r.icon as string | null) : prev.icon,
    aliases: Array.isArray(r.aliases) ? (r.aliases as string[]) : prev.aliases,
    archived: typeof r.archived === 'boolean' ? r.archived : prev.archived,
    tax: (r.tax as Label['tax']) ?? prev.tax,
  };
  state.labels = state.labels.map((x) => (x.id === m[2] ? next : x));
  return next;
});
route('DELETE', /^\/pf\/([^/]+)\/labels\/([^/]+)$/, ({ m }) => {
  if (!state.labels.some((l) => l.id === m[2])) throw new HttpError(404, `label ${m[2]} not found`);
  if (pfLabelInUse(m[2])) throw new HttpError(409, `label ${m[2]} has entries; archive it instead`);
  state.labels = state.labels.filter((l) => l.id !== m[2]);
  return { ok: true };
});

/* credit: cards, MSI, loans, scores */
route('POST', /^\/pf\/([^/]+)\/credit\/cards$/, ({ body }) => {
  const currency = str(body, 'currency', 'MXN');
  const card: CreditCard = {
    id: nextId('card'),
    name: str(body, 'name'),
    account: str(body, 'account'),
    balance: amt('0', currency),
    limit: amt(str(body, 'limit_amount', '0'), currency),
    utilization: '0.0000',
    next_cut_date: nextDay(num(body, 'cut_day', 1)),
    next_due_date: nextDay(num(body, 'due_day', 20)),
    pago_no_intereses: amt('0', currency),
    minimum_payment_note: "(verify) minimum payment is set by the issuer's cardholder agreement",
    msi: [],
    explain: plainExplain('Pago para no generar intereses = saldo al corte, completo.'),
  };
  state.cards = [...state.cards, card];
  return card;
});
route('POST', /^\/pf\/([^/]+)\/credit\/cards\/([^/]+)\/msi$/, ({ m, body }) => {
  const card = state.cards.find((c) => c.id === m[2]);
  if (!card) throw new HttpError(404, `No existe la tarjeta ${m[2]}.`);
  const months = Math.max(1, num(body, 'months', 12));
  const paid = num(body, 'paid_months', 0);
  const currency = str(body, 'currency', card.balance.currency);
  const total = toCents(str(body, 'amount', '0'));
  const monthly = total / BigInt(months);
  const remaining = monthly * BigInt(Math.max(0, months - paid));
  const plan = {
    description: str(body, 'purchase'),
    months_total: months,
    months_left: Math.max(0, months - paid),
    monthly: amt(fromCents(monthly), currency),
    remaining: amt(fromCents(remaining), currency),
  };
  const updated: CreditCard = { ...card, msi: [...card.msi, plan] };
  state.cards = state.cards.map((c) => (c.id === card.id ? updated : c));
  return plan;
});
route('POST', /^\/pf\/([^/]+)\/credit\/loans$/, ({ body }) => {
  const loan: Loan = {
    id: nextId('loan'),
    ws_id: WS_ID,
    account: str(body, 'account'),
    name: str(body, 'name'),
    principal: str(body, 'principal', '0'),
    currency: str(body, 'currency', 'MXN'),
    annual_rate: str(body, 'annual_rate', '0'),
    months: num(body, 'months', 12),
    start: str(body, 'start'),
  };
  state.loans = [...state.loans, loan];
  return loan;
});
route('GET', /^\/pf\/([^/]+)\/credit\/scores$/, () => state.scores);
route('POST', /^\/pf\/([^/]+)\/credit\/scores$/, ({ body }) => {
  const score: CreditScore = {
    id: nextId('score'),
    ws_id: WS_ID,
    bureau: str(body, 'bureau'),
    score: num(body, 'score', 0),
    date: str(body, 'date'),
  };
  state.scores = [score, ...state.scores];
  return score;
});
route('DELETE', /^\/pf\/([^/]+)\/credit\/scores\/([^/]+)$/, ({ m }) => {
  if (!state.scores.some((x) => x.id === m[2])) throw new HttpError(404, `No existe el puntaje ${m[2]}.`);
  state.scores = state.scores.filter((x) => x.id !== m[2]);
  return { ok: true };
});

/* ledger transactions */
function requireBalanced(txn: Transaction): void {
  if (!txn || !Array.isArray(txn.postings) || txn.postings.length < 2) {
    throw new HttpError(422, 'Una transacción necesita al menos dos movimientos.');
  }
  const blanks = txn.postings.filter((p) => !p.amount);
  if (blanks.length > 1) throw new HttpError(422, 'Sólo un movimiento puede quedar sin importe.');
  if (blanks.length === 0) {
    let total = 0n;
    for (const p of txn.postings) total += toCents(p.amount!.amount);
    if (total !== 0n) throw new HttpError(422, `Los movimientos no cuadran por ${fromCents(total)}.`);
  }
}

/** Fill the single blank posting, exactly as Beancount would. */
function balance(txn: Transaction): Transaction {
  const blankIndex = txn.postings.findIndex((p) => !p.amount);
  if (blankIndex < 0) return txn;
  let total = 0n;
  let currency = 'MXN';
  for (const p of txn.postings) {
    if (!p.amount) continue;
    total += toCents(p.amount.amount);
    currency = p.amount.currency;
  }
  return {
    ...txn,
    postings: txn.postings.map((p, i) =>
      i === blankIndex ? { ...p, amount: amt(fromCents(-total), currency) } : p,
    ),
  };
}

route('POST', /^\/ledger\/([^/]+)\/transactions$/, ({ body }) => {
  const txn = body as Transaction;
  requireBalanced(txn);
  const txnId = nextId('txn');
  const stored = balance({ ...txn, links: [txnId, ...(txn.links ?? [])], meta: { source: 'manual', ...(txn.meta ?? {}) } });
  state.journal = [stored, ...state.journal];
  return { txn_id: txnId, warnings: [] };
});
route('PUT', /^\/ledger\/([^/]+)\/transactions\/([^/]+)$/, ({ m, body }) => {
  const i = state.journal.findIndex((tx) => tx.links.includes(m[2]));
  if (i < 0) throw new HttpError(404, `No existe la transacción ${m[2]}.`);
  const txn = body as Transaction;
  requireBalanced(txn);
  const stored = balance({ ...txn, links: [m[2], ...(txn.links ?? []).filter((l) => l !== m[2])] });
  state.journal = state.journal.map((tx, j) => (j === i ? stored : tx));
  return { txn_id: m[2], warnings: [] };
});
route('DELETE', /^\/ledger\/([^/]+)\/transactions\/([^/]+)$/, ({ m }) => {
  const target = state.journal.find((tx) => tx.links.includes(m[2]));
  if (!target) throw new HttpError(404, `No existe la transacción ${m[2]}.`);
  // Never erase history: tag the original and book the reversing entry.
  const voided: Transaction = { ...target, tags: [...target.tags, 'voided'] };
  const reversal: Transaction = {
    ...target,
    narration: `REVERSA: ${target.narration}`,
    tags: [...target.tags, 'voided'],
    links: [nextId('txn')],
    postings: target.postings.map((p) => ({
      account: p.account,
      amount: p.amount ? amt(fromCents(-toCents(p.amount.amount)), p.amount.currency) : null,
    })),
  };
  state.journal = [reversal, ...state.journal.map((tx) => (tx === target ? voided : tx))];
  return { txn_id: m[2], warnings: ['voided'] };
});

/* statements */
function sectionFor(title: string, prefixes: string[], start: string, end: string, sign: 1n | -1n): StatementSection {
  const totals = new Map<string, bigint>();
  for (const tx of state.journal) {
    if (tx.date < start || tx.date > end) continue;
    if (tx.tags.includes('voided')) continue;
    for (const p of balance(tx).postings) {
      if (!p.amount) continue;
      if (!prefixes.some((pre) => p.account.startsWith(pre))) continue;
      totals.set(p.account, (totals.get(p.account) ?? 0n) + toCents(p.amount.amount) * sign);
    }
  }
  let total = 0n;
  const rows = [...totals.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([acct, cents]) => {
      total += cents;
      return { account: acct, label: acct.split(':').pop() ?? acct, amount: amt(fromCents(cents)) };
    });
  return { title, rows, total: amt(fromCents(total)) };
}

route('GET', /^\/ledger\/([^/]+)\/statements\/(\d{4}(?:-\d{2})?)$/, ({ m, url }) => {
  const type = (url.searchParams.get('type') ?? 'pnl') as StatementType;
  const p = m[2];
  const start = p.length === 4 ? `${p}-01-01` : `${p}-01`;
  const end = p.length === 4 ? `${p}-12-31` : `${p}-31`;
  let sections: StatementSection[];
  if (type === 'balance') {
    sections = [
      sectionFor('Assets', ['Assets:'], '0000-01-01', end, 1n),
      sectionFor('Liabilities', ['Liabilities:'], '0000-01-01', end, 1n),
      sectionFor('Equity', ['Equity:'], '0000-01-01', end, 1n),
    ];
  } else if (type === 'cashflow') {
    sections = [
      sectionFor('Bank', ['Assets:Bank:'], start, end, 1n),
      sectionFor('Cash', ['Assets:Cash'], start, end, 1n),
    ];
  } else {
    sections = [
      sectionFor('Income', ['Income:'], start, end, -1n),
      sectionFor('Expenses', ['Expenses:'], start, end, 1n),
    ];
  }
  let net = 0n;
  for (const sec of sections) net += toCents(sec.total.amount) * (type === 'pnl' && sec.title === 'Expenses' ? -1n : 1n);
  const statement: Statement = {
    type,
    period: p,
    currency: 'MXN',
    sections,
    net: amt(fromCents(net)),
    explain: plainExplain(
      type === 'pnl'
        ? 'Resultados del periodo: ingresos menos gastos, sobre las transacciones del libro.'
        : type === 'balance'
          ? 'Balance al cierre del periodo: activos, pasivos y capital acumulados.'
          : 'Flujo de efectivo: variación de bancos y efectivo en el periodo.',
      sections.map((sec) => ({ label: sec.title, value: sec.total.amount })),
    ),
  };
  return statement;
});

/* reconcile */
function reconcileBoard(period: string) {
  const start = `${period}-01`;
  const end = `${period}-31`;
  const bankTxns = state.journal.filter(
    (tx) => tx.date >= start && tx.date <= end && tx.postings.some((p) => p.account.startsWith('Assets:Bank:')),
  );
  const docs = state.cfdis.filter((c) => c.fecha.startsWith(period));
  const bank_lines: ReconcileBankLine[] = bankTxns.map((tx, i) => {
    const id = tx.links[0] ?? `bank-${period}-${i}`;
    const leg = tx.postings.find((p) => p.account.startsWith('Assets:Bank:'));
    const amount = leg?.amount ?? amt('0');
    const stored = state.matches[id];
    const fromMeta = tx.meta.cfdi_uuid ? { cfdi_uuid: tx.meta.cfdi_uuid } : undefined;
    const match = stored ?? fromMeta;
    const cents = toCents(amount.amount);
    const abs = cents < 0n ? -cents : cents;
    const suggestions = match
      ? []
      : docs
          .filter((d) => {
            const dc = toCents(d.total);
            return dc === abs || dc === -abs;
          })
          .slice(0, 3)
          .map((d) => ({ txn_id: null, cfdi_uuid: d.uuid, score: 0.92 }));
    return {
      id,
      date: tx.date,
      description: `${tx.payee ? `${tx.payee} — ` : ''}${tx.narration}`,
      amount,
      matched_txn_id: match?.txn_id ?? null,
      cfdi_uuid: match?.cfdi_uuid ?? null,
      suggestions,
    };
  });
  const matchedUuids = new Set(bank_lines.map((b) => b.cfdi_uuid).filter(Boolean) as string[]);
  return {
    bank_lines,
    unmatched_bank: bank_lines.filter((b) => !b.matched_txn_id && !b.cfdi_uuid).length,
    unmatched_cfdi: docs.filter((d) => !matchedUuids.has(d.uuid)).map((d) => d.uuid),
    explain: plainExplain(
      'Se sugiere una conciliación cuando el importe del movimiento bancario coincide exactamente con el total del CFDI.',
      [{ label: 'bank_lines', value: String(bank_lines.length) }],
    ),
  };
}

route('GET', /^\/ingest\/([^/]+)\/reconcile$/, ({ url }) =>
  reconcileBoard(url.searchParams.get('period') ?? DEMO_PERIOD),
);
route('POST', /^\/ingest\/([^/]+)\/reconcile\/match$/, ({ body }) => {
  const id = str(body, 'bank_line_id');
  if (!id) throw new HttpError(422, 'Falta bank_line_id.');
  const txnId = str(body, 'txn_id');
  const uuid = str(body, 'cfdi_uuid');
  if (!txnId && !uuid) throw new HttpError(422, 'Se necesita txn_id o cfdi_uuid.');
  state.matches[id] = { ...(txnId ? { txn_id: txnId } : {}), ...(uuid ? { cfdi_uuid: uuid } : {}) };
  return reconcileBoard(DEMO_PERIOD);
});
route('POST', /^\/ingest\/([^/]+)\/reconcile\/unmatch$/, ({ body }) => {
  const id = str(body, 'bank_line_id');
  delete state.matches[id];
  // A match that came from the transaction's own meta is removed there too.
  state.journal = state.journal.map((tx) =>
    tx.links[0] === id && tx.meta.cfdi_uuid
      ? { ...tx, meta: Object.fromEntries(Object.entries(tx.meta).filter(([k]) => k !== 'cfdi_uuid')) }
      : tx,
  );
  return reconcileBoard(DEMO_PERIOD);
});


/* ============================= US tax, cross-border, holdings, plan, credit */
/**
 * These endpoints are answered from ./fixtures-tax with the same discipline as the rest of the
 * mock: decimal *strings* everywhere, integer-centavo BigInt arithmetic wherever the mock has
 * to produce a new figure (trades, prices, sensitivity), and the real 404 for a missing FX
 * rate so the UI's "no rate" state is actually exercised.
 */

const state2 = {
  /** The cross-border profile the wizard writes, per workspace. */
  xb: { [US_WS_ID]: clone(XB_PROFILE) } as Record<string, CrossborderProfile>,
  holdings: {} as Record<string, HoldingsOverview>,
  /** `${symbol}` -> latest manual price, per workspace. */
  prices: {} as Record<string, Record<string, { amount: string; currency: string; date: string }>>,
  creditImports: clone(CREDIT_IMPORTS) as CreditReportImport[],
  saved: [] as SavedScenario[],
  /** Seeded so one pair resolves and every other pair 404s, like the real offline API. */
  fx: { 'USD/MXN': { rate: '18.4210', source: 'fixture' } } as Record<
    string,
    { rate: string; source: string }
  >,
};

const holdingsOf = (ws: string): HoldingsOverview => {
  if (!state2.holdings[ws]) state2.holdings[ws] = holdingsSeed(ws);
  return state2.holdings[ws];
};

/** Recompute market value / unrealized / allocation from whatever prices are on record. */
function repriceHoldings(ws: string): HoldingsOverview {
  const h = holdingsOf(ws);
  const prices = state2.prices[ws] ?? {};
  let totalCents = 0n;
  const byClass: Record<string, bigint> = {};

  h.positions = h.positions.map((p) => {
    const px = prices[p.symbol];
    if (!px) return { ...p, market_value: null, unrealized_gain: null, price_as_of: null };
    // units are whole-or-decimal strings; work in centavos × units to stay exact enough.
    const unitCents = toCents(px.amount);
    const [uInt = '0', uFrac = ''] = p.units.split('.');
    const unitsMilli = BigInt(uInt) * 1000n + BigInt((uFrac + '000').slice(0, 3));
    const mvCents = (unitCents * unitsMilli) / 1000n;
    const gainCents = mvCents - toCents(p.cost_basis.amount);
    totalCents += mvCents;
    const cls = p.asset_class ?? 'other';
    byClass[cls] = (byClass[cls] ?? 0n) + mvCents;
    return {
      ...p,
      market_value: { amount: fromCents(mvCents), currency: px.currency },
      unrealized_gain: { amount: fromCents(gainCents), currency: px.currency },
      price_as_of: px.date,
    };
  });

  h.allocation = {
    by_asset_class: Object.fromEntries(Object.entries(byClass).map(([k, v]) => [k, fromCents(v)])),
    total_market_value: fromCents(totalCents),
  };
  return h;
}

/* tax/us + tx franchise */
route('GET', /^\/tax\/us\/([^/]+)\/(\d{4})$/, ({ m }) => {
  const ws = m[1];
  const year = Number(m[2]);
  if (ws !== US_WS_ID) {
    throw new HttpError(404, `El espacio ${ws} no incluye la jurisdicción US.`);
  }
  return { ...clone(US_TAX), workspace: ws, year };
});
route('GET', /^\/tax\/us\/([^/]+)\/(\d{4})\/tx-franchise$/, ({ m }) => {
  const ws = m[1];
  if (ws !== US_WS_ID) throw new HttpError(404, `El espacio ${ws} no incluye la jurisdicción US.`);
  return { ...clone(TX_FRANCHISE), workspace: ws, year: Number(m[2]) };
});

/* crossborder */
route('GET', /^\/crossborder\/([^/]+)\/assessment$/, ({ m }) => {
  const p = state2.xb[m[1]] ?? clone(XB_PROFILE);
  return { ...xbAssessment(p), workspace: m[1] };
});
route('PUT', /^\/crossborder\/([^/]+)\/profile$/, ({ m, body }) => {
  const next = { ...clone(XB_PROFILE), ...(body as Partial<CrossborderProfile>) };
  state2.xb[m[1]] = next;
  return { workspace: m[1], crossborder: next };
});

/* holdings */
route('GET', /^\/holdings\/([^/]+)$/, ({ m }) => repriceHoldings(m[1]));

route('POST', /^\/holdings\/([^/]+)\/trades$/, ({ m, body }) => {
  const ws = m[1];
  const h = holdingsOf(ws);
  const b = asRecord(body);
  const price = (b.price ?? {}) as { amount?: string; currency?: string };
  const symbol = str(body, 'symbol').toUpperCase();
  const units = str(body, 'units', '0');
  const kind = str(body, 'kind', 'buy');
  const account = str(body, 'account', 'Assets:Investments:Brokerage');
  const currency = price.currency ?? 'USD';
  if (!symbol) throw new HttpError(422, 'Falta el símbolo.');
  if (!units || units === '0') throw new HttpError(422, 'Los títulos son obligatorios.');

  // cost = units × price, exact in centavos.
  const [uInt = '0', uFrac = ''] = units.split('.');
  const unitsMilli = BigInt(uInt.replace('-', '')) * 1000n + BigInt((uFrac + '000').slice(0, 3));
  const costCents = (toCents(price.amount ?? '0') * unitsMilli) / 1000n;

  if (kind === 'buy') {
    const existing = h.positions.find((p) => p.symbol === symbol && p.account === account);
    if (existing) {
      const [eInt = '0', eFrac = ''] = existing.units.split('.');
      const total = BigInt(eInt) * 1000n + BigInt((eFrac + '000').slice(0, 3)) + unitsMilli;
      existing.units = String(Number(total) / 1000);
      existing.cost_basis = {
        amount: fromCents(toCents(existing.cost_basis.amount) + costCents),
        currency,
      };
    } else {
      const meta = h.symbols.find((s) => s.symbol === symbol);
      h.positions.push({
        symbol,
        account,
        units,
        cost_basis: { amount: fromCents(costCents), currency },
        market_value: null,
        unrealized_gain: null,
        asset_class: meta?.asset_class ?? 'other',
        name: meta?.name ?? null,
        price_as_of: null,
      });
    }
  } else if (kind === 'sell') {
    const pos = h.positions.find((p) => p.symbol === symbol && p.account === account);
    if (!pos) throw new HttpError(422, `No hay posición abierta en ${symbol}.`);
    const [eInt = '0', eFrac = ''] = pos.units.split('.');
    const held = BigInt(eInt) * 1000n + BigInt((eFrac + '000').slice(0, 3));
    if (unitsMilli > held) throw new HttpError(422, `Sólo tienes ${pos.units} títulos de ${symbol}.`);
    // FIFO against the single aggregate lot the mock keeps.
    const lotCostCents = (toCents(pos.cost_basis.amount) * unitsMilli) / (held || 1n);
    pos.units = String(Number(held - unitsMilli) / 1000);
    pos.cost_basis = { amount: fromCents(toCents(pos.cost_basis.amount) - lotCostCents), currency };
    h.realized_gains.unshift({
      symbol,
      date: str(body, 'date', new Date().toISOString().slice(0, 10)),
      units,
      proceeds: { amount: fromCents(costCents), currency },
      cost_basis: { amount: fromCents(lotCostCents), currency },
      gain: { amount: fromCents(costCents - lotCostCents), currency },
      acquired: null,
    });
    if (pos.units === '0') h.positions = h.positions.filter((p) => p !== pos);
  } else if (kind === 'contribution') {
    const key = str(body, 'limit_key');
    const limit = h.contributions.limits.find((l) => l.key === key);
    if (limit) {
      limit.contributed = { ...limit.contributed, amount: fromCents(toCents(limit.contributed.amount) + costCents) };
      limit.remaining = { ...limit.remaining, amount: fromCents(toCents(limit.limit.amount) - toCents(limit.contributed.amount)) };
    }
  }

  const id = nextId('trade');
  repriceHoldings(ws);
  return {
    id,
    ws_id: ws,
    date: str(body, 'date'),
    account,
    symbol,
    kind,
    units,
    price_amount: price.amount ?? '0',
    price_currency: currency,
    txn_id: id,
    created_at: new Date().toISOString(),
  };
});

route('POST', /^\/holdings\/([^/]+)\/prices$/, ({ m, body }) => {
  const ws = m[1];
  const b = asRecord(body);
  const price = (b.price ?? {}) as { amount?: string; currency?: string };
  const symbol = str(body, 'symbol').toUpperCase();
  const date = str(body, 'date', new Date().toISOString().slice(0, 10));
  if (!symbol || !price.amount) throw new HttpError(422, 'Símbolo y precio son obligatorios.');
  state2.prices[ws] = {
    ...(state2.prices[ws] ?? {}),
    [symbol]: { amount: price.amount, currency: price.currency ?? 'USD', date },
  };
  repriceHoldings(ws);
  return { symbol, date };
});

/* fx — a seeded pair resolves, everything else 404s exactly like the offline API */
route('GET', /^\/fx\/rate$/, ({ url }) => {
  const base = (url.searchParams.get('base') ?? 'USD').toUpperCase();
  const quote = (url.searchParams.get('quote') ?? 'MXN').toUpperCase();
  const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10);
  const hit = state2.fx[`${base}/${quote}`];
  if (!hit) throw new HttpError(404, `no FX rate for ${base}/${quote} on ${date}`);
  return { base, quote, date, rate: hit.rate, source: hit.source };
});

/* creditreport */
route('GET', /^\/creditreport\/([^/]+)$/, ({ m }) => {
  const imports = state2.creditImports.filter((i) => i.ws_id === m[1]);
  return { imports, latest: imports[0] ?? null };
});
route('GET', /^\/creditreport\/([^/]+)\/explain$/, () => clone(CREDIT_EXPLAIN));
route('POST', /^\/creditreport\/([^/]+)\/import$/, ({ m, init }) => {
  const form = init?.body instanceof FormData ? init.body : null;
  const file = form?.get('file');
  const filename = file instanceof File ? file.name : 'reporte.pdf';
  // The mock cannot parse a PDF, so it stores a clearly-labelledlow-confidence import rather
  // than inventing accounts: exactly what the real parser does with an unreadable file.
  const imported: CreditReportImport = {
    id: nextId('crimp'),
    ws_id: m[1],
    filename,
    imported_at: new Date().toISOString(),
    score: null,
    accounts: [],
    warnings: [
      'Modo demostración: el PDF no se interpreta en el navegador, así que no se extrajo ninguna cuenta ni score.',
    ],
  };
  state2.creditImports.unshift(imported);
  return imported;
});

/* plan */
route('GET', /^\/plan\/([^/]+)\/scenarios$/, () => clone(SCENARIOS));

route('POST', /^\/plan\/([^/]+)\/scenarios\/([^/]+)\/run$/, ({ m, body }) => {
  const fixture = SCENARIO_RESULTS[m[2]];
  if (!fixture) throw new HttpError(404, `Escenario desconocido: ${m[2]}`);
  return {
    inputs: asRecord(body),
    results: clone(fixture.results),
    explain: {
      summary: fixture.summary,
      steps: Object.entries(fixture.results)
        .filter(([, v]) => typeof v === 'string')
        .map(([k, v]) => ({ label: k, formula: null, value: String(v) })),
      citations: [],
      rule_versions: fixture.rules,
      confidence: null,
    },
  };
});

route('POST', /^\/plan\/([^/]+)\/scenarios\/([^/]+)\/sensitivity$/, ({ m, body }) => {
  const spec = SCENARIOS.find((s) => s.id === m[2]);
  const fixture = SCENARIO_RESULTS[m[2]];
  if (!spec || !fixture) throw new HttpError(404, `Escenario desconocido: ${m[2]}`);
  const b = asRecord(body);
  const vary = Array.isArray(b.vary) ? (b.vary as string[]) : [];
  const pct = BigInt(Math.round(num(body, 'range_pct', 10)));

  // The metric the catalog points at, walked out of the fixture results.
  const metric = spec.metric_path.slice(1).reduce<unknown>((acc, k) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[k];
    return undefined;
  }, fixture.results);
  const baseCents = toCents(typeof metric === 'string' ? metric : '0');

  const rows = vary.map((field) => {
    const low = (baseCents * (100n - pct)) / 100n;
    const high = (baseCents * (100n + pct)) / 100n;
    return {
      field,
      low: fromCents(low),
      base: fromCents(baseCents),
      high: fromCents(high),
      range: fromCents(high - low),
    };
  });

  return {
    metric_path: spec.metric_path,
    rows,
    explain: plainExplain(
      `Cada campo se movió ±${pct}% alrededor de su valor y el escenario se volvió a correr; la amplitud ordena qué supuesto pesa más.`,
      rows.map((r) => ({ label: r.field, value: r.range })),
    ),
  };
});

route('POST', /^\/plan\/([^/]+)\/scenarios\/([^/]+)\/montecarlo$/, ({ m, body }) => {
  const fixture = SCENARIO_RESULTS.retirement;
  const inputs = asRecord(body).inputs;
  const n = Math.round(num(body, 'n', 200));
  const seed = Math.round(num(body, 'seed', 7));
  const r = fixture.results as Record<string, string>;
  return {
    inputs: (inputs ?? {}) as Record<string, string | number | boolean>,
    results: {
      p10: r.p10,
      p50: r.p50,
      p90: r.p90,
      mean: r.mean,
      success_rate_pct: r.success_rate_pct,
      iterations: n,
      seed,
    },
    explain: plainExplain(
      `Con ${n} simulaciones (seed ${seed}): saldo final p50 = ${r.p50} (rango p10-p90: ${r.p10} - ${r.p90}). Escenario: ${m[2]}.`,
      [
        { label: 'p10', value: r.p10 },
        { label: 'p50', value: r.p50 },
        { label: 'p90', value: r.p90 },
      ],
    ),
  };
});

route('GET', /^\/plan\/([^/]+)\/saved$/, ({ m }) => state2.saved.filter((s) => s.ws_id === m[1]));
route('POST', /^\/plan\/([^/]+)\/saved$/, ({ m, body }) => {
  const b = asRecord(body);
  const row: SavedScenario = {
    id: nextId('plansaved'),
    ws_id: m[1],
    scenario_id: str(body, 'scenario_id'),
    name: str(body, 'name'),
    inputs: (b.inputs ?? {}) as Record<string, string | number | boolean>,
    created_at: new Date().toISOString(),
    updated_at: null,
  };
  if (!row.name) throw new HttpError(422, 'El nombre es obligatorio.');
  state2.saved.unshift(row);
  return row;
});
route('DELETE', /^\/plan\/([^/]+)\/saved\/([^/]+)$/, ({ m }) => {
  state2.saved = state2.saved.filter((s) => s.id !== m[2]);
  return { ok: true };
});

/* research refs */
route('GET', /^\/research\/refs$/, ({ url }) => {
  const law = url.searchParams.get('law') ?? '';
  const article = url.searchParams.get('article') ?? '';
  return REFS[`${law}|${article}`] ?? { law, article, cites: [], cited_by: [] };
});

/* watch sources + history + proposals */
route('GET', /^\/watch\/sources$/, () => clone(WATCH_SOURCES));
route('GET', /^\/watch\/sources\/([^/]+)\/history$/, ({ m }) =>
  WATCH_HISTORY[m[1]] ?? { source_id: m[1], snapshots: [], changes: [] },
);
route('GET', /^\/watch\/proposals$/, () => clone(WATCH_PROPOSALS));

/* ========================================================= business routes */
/**
 * The business endpoints answer from the recorded `demo-biz` responses. Payroll keeps a
 * little state so a run really appears in the list afterwards, the way it does against the
 * real API.
 */

const state3 = {
  payrollRuns: clone(PAYROLL_RUNS) as typeof PAYROLL_RUNS,
  /** insight ids dismissed since the page loaded, per workspace. */
  dismissed: {} as Record<string, string[]>,
  archive: clone(ARCHIVE_SEED) as typeof ARCHIVE_SEED,
  workflows: [] as WorkflowSeed[],
  runs: [] as WorkflowRun[],
};

route('GET', /^\/business\/constants\/mx-nl$/, () => clone(BIZ_CONSTANTS));

route('GET', /^\/business\/([^/]+)\/kpis$/, ({ url }) => {
  const period = url.searchParams.get('period') ?? DEMO_PERIOD;
  return bizKpis(period);
});

route('GET', /^\/business\/([^/]+)\/invoices$/, () => clone(INVOICE_REGISTER));

route('POST', /^\/business\/([^/]+)\/invoices\/remind$/, ({ body }) => {
  const uuid = str(body, 'uuid');
  const inv = INVOICE_REGISTER.open_invoices.find((i) => i.uuid === uuid);
  if (!inv) throw new HttpError(404, `unknown invoice ${uuid}`);
  const client = str(body, 'client_name') || inv.client_rfc;
  return {
    uuid: inv.uuid,
    client_rfc: inv.client_rfc,
    outstanding: inv.outstanding,
    age_days: inv.age_days,
    bucket: inv.bucket,
    paid: false,
    text: {
      es:
        `Hola ${client}: le recordamos la factura ${inv.uuid} del ${inv.fecha} por ` +
        `${inv.total.amount} ${inv.total.currency}, con ${inv.outstanding.amount} pendiente ` +
        `(${inv.age_days} días). Quedamos atentos al comprobante de pago para emitir el REP.`,
      en:
        `Hello ${client}: a reminder about invoice ${inv.uuid} dated ${inv.fecha} for ` +
        `${inv.total.amount} ${inv.total.currency}, ${inv.outstanding.amount} still outstanding ` +
        `(${inv.age_days} days). Please send the payment receipt so we can issue the REP.`,
    },
    sent: false,
    note: 'Aurum never sends messages; copy this text into your own email or WhatsApp.',
  };
});

route('GET', /^\/business\/([^/]+)\/payroll\/employees$/, () => clone(EMPLOYEES));

route('GET', /^\/business\/([^/]+)\/payroll$/, ({ url }) => {
  const period = url.searchParams.get('period');
  return state3.payrollRuns.filter((r) => !period || r.period === period);
});

route('POST', /^\/business\/([^/]+)\/payroll\/run$/, ({ body }) => {
  const period = str(body, 'period');
  if (!/^\d{4}-\d{2}$/.test(period)) throw new HttpError(422, 'period debe ser YYYY-MM');
  const days = str(body, 'days') || '31';
  const id = `pay-${period}-${(state.seq += 1).toString(16)}`;
  const run = payrollRun(id, period, days);
  state3.payrollRuns.unshift({
    id: run.id,
    period,
    days,
    currency: run.currency,
    gross: run.totals.gross.amount,
    net: run.totals.net.amount,
    isr_retenido: run.totals.isr_retenido.amount,
    imss_employee: run.totals.imss_employee.amount,
    imss_employer: run.totals.imss_employer.amount,
    infonavit: run.totals.infonavit.amount,
    isn: run.totals.isn.amount,
    employer_cost: run.totals.employer_cost.amount,
    txn_id: run.txn_id,
    created_at: new Date().toISOString(),
  });
  return run;
});

route('GET', /^\/business\/([^/]+)\/payroll\/([^/]+)$/, ({ m }) => {
  const row = state3.payrollRuns.find((r) => r.id === m[2]);
  if (!row) throw new HttpError(404, `unknown payroll run ${m[2]}`);
  return payrollRun(row.id, row.period, row.days);
});

/* ========================================================= insights routes */

const liveInsights = (ws: string, period: string) => {
  const dismissed = state3.dismissed[ws] ?? [];
  return insightsFor(ws, period).filter((i) => !dismissed.includes(i.id));
};

route('GET', /^\/insights\/([^/]+)\/digest$/, ({ m, url }) => {
  const period = url.searchParams.get('period') ?? DEMO_PERIOD;
  const list = liveInsights(m[1], period);
  return {
    workspace: m[1],
    period,
    text: digestFor(m[1], period, list),
    urgent_count: list.filter((i) => i.severity === 'urgent').length,
    insights: list,
  };
});

route('GET', /^\/insights\/([^/]+)\/calendar$/, ({ m, url }) =>
  calendarFor(m[1], url.searchParams.get('from') ?? '', url.searchParams.get('to') ?? ''),
);

route('GET', /^\/insights\/([^/]+)$/, ({ m, url }) =>
  liveInsights(m[1], url.searchParams.get('period') ?? DEMO_PERIOD),
);

route('POST', /^\/insights\/([^/]+)\/([^/]+)\/dismiss$/, ({ m }) => {
  const list = state3.dismissed[m[1]] ?? (state3.dismissed[m[1]] = []);
  if (!list.includes(m[2])) list.push(m[2]);
  return { ok: true, ws_id: m[1], insight_id: m[2] };
});

/* ========================================================== reports routes */

const wsKind = (ws: string) => {
  const w = state.workspaces.find((x) => x.id === ws);
  return { kind: w?.kind ?? 'personal', jurisdictions: (w?.jurisdictions ?? ['MX']) as string[] };
};

route('GET', /^\/reports\/([^/]+)$/, ({ m }) => {
  const { kind, jurisdictions } = wsKind(m[1]);
  return reportCatalog(m[1], kind, jurisdictions);
});

route('GET', /^\/reports\/([^/]+)\/([^/]+)\/preview$/, ({ m, url }) =>
  reportPreview(
    m[1],
    m[2],
    url.searchParams.get('period'),
    (url.searchParams.get('lang') as 'es' | 'en') ?? 'es',
  ),
);

route('GET', /^\/reports\/([^/]+)\/([^/]+)\/archive$/, ({ m }) => {
  const rows = state3.archive.filter((a) => a.pack === m[2] && (a.ws_id ?? a.workspace) === m[1]);
  // The real API 404s a pack that has never been archived; the screen renders that as empty.
  if (rows.length === 0) throw new HttpError(404, `no archived reports for '${m[2]}'`);
  return rows;
});

route('POST', /^\/reports\/([^/]+)\/([^/]+)\/archive$/, ({ m, url }) => {
  const record = {
    id: `rep-${(state.seq += 1).toString(16)}`,
    ws_id: m[1],
    workspace: m[1],
    pack: m[2],
    period: url.searchParams.get('period'),
    format: url.searchParams.get('format') ?? 'pdf',
    path: `(mock)/docs/reports/${m[2]}.pdf`,
    sha256: `${(state.seq * 7919).toString(16)}`.repeat(16).slice(0, 64),
    created_at: new Date().toISOString(),
    size: 48213,
  };
  state3.archive.unshift(record);
  return record;
});

route('GET', /^\/reports\/([^/]+)\/([^/]+)$/, ({ m, url }) => {
  const preview = reportPreview(
    m[1],
    m[2],
    url.searchParams.get('period'),
    (url.searchParams.get('lang') as 'es' | 'en') ?? 'es',
  );
  return { __text: reportHtml(preview), __type: 'text/html; charset=utf-8' };
});

/* ======================================================== workflows routes */
/* Verified against the real API (2026-09). GET /{ws} is a bare summary list (no yaml); the
   yaml + parsed definition only come back from GET /{ws}/{id}. Runs carry a per-step trace
   with an HTTP status/duration; the runs list (GET /{ws}/{id}/runs) does not include steps. */

const workflowsFor = (ws: string) => {
  if (state3.workflows.length === 0) {
    state3.workflows = clone(WORKFLOWS_SEED).map((w) => ({ ...w, workspace: ws }));
  }
  return state3.workflows.filter((w) => w.workspace === ws || w.workspace === '');
};

const toSummary = (w: WorkflowSeed) => ({
  id: w.id,
  workspace: w.workspace,
  name: w.name,
  schedule: w.schedule,
  created_at: w.created_at,
  updated_at: w.updated_at,
});

const toDetail = (w: WorkflowSeed) => ({
  workspace: w.workspace,
  id: w.id,
  yaml: w.yaml,
  valid: true,
  errors: [] as string[],
  warnings: [] as string[],
  definition: w.definition,
});

route('GET', /^\/workflows\/catalog$/, () => clone(WORKFLOW_CATALOG));

route('GET', /^\/workflows\/([^/]+)$/, ({ m }) => workflowsFor(m[1]).map(toSummary));

route('GET', /^\/workflows\/([^/]+)\/([^/]+)$/, ({ m }) => {
  const wf = workflowsFor(m[1]).find((w) => w.id === m[2]);
  if (!wf) throw new HttpError(404, `unknown workflow ${m[2]}`);
  return toDetail(wf);
});

route('POST', /^\/workflows\/([^/]+)\/propose$/, ({ m, body }) => {
  const description = str(body, 'description');
  if (!description.trim()) throw new HttpError(422, 'description is required');
  return {
    workspace: m[1],
    source: 'offline-fallback',
    yaml: `${PROPOSED_YAML}# ${description.slice(0, 120)}\n`,
    valid: true,
    errors: [] as string[],
    warnings: [
      'Propuesta del modelo: revísala antes de guardarla. Aurum nunca guarda ni ejecuta una propuesta por su cuenta.',
    ],
  };
});

/** Parse just enough of the yaml to keep `definition` roughly in sync with what was typed —
    the real API does the real parse; this only needs to be plausible for the mock. */
function parseYamlSteps(yaml: string) {
  const lines = yaml.split(/\r?\n/);
  const ids = lines.filter((l) => /^\s*-\s*id\s*:/.test(l)).map((l) => l.split(':').slice(1).join(':').trim());
  const methods = lines.filter((l) => /^\s*method\s*:/.test(l)).map((l) => l.split(':').slice(1).join(':').trim());
  const paths = lines.filter((l) => /^\s*path\s*:/.test(l)).map((l) => l.split(':').slice(1).join(':').trim());
  return ids.map((id, i) => ({ id, method: methods[i] ?? 'GET', path: paths[i] ?? '—' }));
}

const yamlField = (yaml: string, key: string) => {
  const m2 = new RegExp(`^\\s*${key}\\s*:\\s*(.*)$`, 'm').exec(yaml);
  return m2 ? m2[1].trim() : '';
};

route('POST', /^\/workflows\/([^/]+)$/, ({ m, body }) => {
  const yaml = str(body, 'yaml');
  if (!/steps\s*:/.test(yaml)) throw new HttpError(422, 'the workflow needs a `steps:` block');
  workflowsFor(m[1]);
  const id = yamlField(yaml, 'id') || yamlField(yaml, 'name') || `wf-${(state.seq += 1).toString(16)}`;
  const wf: WorkflowSeed = {
    id,
    workspace: m[1],
    name: yamlField(yaml, 'name') || id,
    schedule: (yamlField(yaml, 'schedule') || null) === 'null' ? null : yamlField(yaml, 'schedule') || null,
    created_at: new Date().toISOString(),
    updated_at: null,
    yaml,
    definition: {
      id,
      name: yamlField(yaml, 'name') || id,
      description: yamlField(yaml, 'description') || null,
      schedule: yamlField(yaml, 'schedule') || null,
      steps: parseYamlSteps(yaml),
    },
  };
  state3.workflows.unshift(wf);
  return toDetail(wf);
});

route('PUT', /^\/workflows\/([^/]+)\/([^/]+)$/, ({ m, body }) => {
  const wf = workflowsFor(m[1]).find((w) => w.id === m[2]);
  if (!wf) throw new HttpError(404, `unknown workflow ${m[2]}`);
  const yaml = str(body, 'yaml');
  if (yaml && !/steps\s*:/.test(yaml)) throw new HttpError(422, 'the workflow needs a `steps:` block');
  if (yaml) {
    wf.yaml = yaml;
    wf.name = yamlField(yaml, 'name') || wf.name;
    wf.schedule = yamlField(yaml, 'schedule') || wf.schedule;
    wf.definition = {
      id: wf.id,
      name: wf.name,
      description: yamlField(yaml, 'description') || null,
      schedule: wf.schedule,
      steps: parseYamlSteps(yaml),
    };
  }
  wf.updated_at = new Date().toISOString();
  return toDetail(wf);
});

route('DELETE', /^\/workflows\/([^/]+)\/([^/]+)$/, ({ m }) => {
  state3.workflows = state3.workflows.filter((w) => w.id !== m[2]);
  return { ok: true };
});

route('POST', /^\/workflows\/([^/]+)\/([^/]+)\/schedule$/, ({ m, body }) => {
  const wf = workflowsFor(m[1]).find((w) => w.id === m[2]);
  if (!wf) throw new HttpError(404, `unknown workflow ${m[2]}`);
  const cron = (asRecord(body).cron ?? null) as string | null;
  if (cron !== null && cron.trim().split(/\s+/).length !== 5) {
    throw new HttpError(422, 'a cron expression has five fields');
  }
  wf.schedule = cron;
  // The mock has no scheduler thread either — it always reports gated, matching the server
  // default (AURUM_WORKFLOWS_SCHEDULER unset).
  return { workspace: m[1], id: wf.id, schedule: wf.schedule, gated: true };
});

route('DELETE', /^\/workflows\/([^/]+)\/([^/]+)\/schedule$/, ({ m }) => {
  const wf = workflowsFor(m[1]).find((w) => w.id === m[2]);
  if (!wf) throw new HttpError(404, `unknown workflow ${m[2]}`);
  wf.schedule = null;
  return { workspace: m[1], id: wf.id, schedule: null, gated: true };
});

route('POST', /^\/workflows\/([^/]+)\/([^/]+)\/run$/, ({ m }) => {
  const wf = workflowsFor(m[1]).find((w) => w.id === m[2]);
  if (!wf) throw new HttpError(404, `unknown workflow ${m[2]}`);
  const runId = `run-${(state.seq += 1).toString(16)}`;
  const startedAt = new Date().toISOString();
  const steps: WorkflowRunStep[] = (wf.definition.steps.length > 0
    ? wf.definition.steps
    : parseYamlSteps(wf.yaml)
  ).map((s, i) => ({
    run_id: runId,
    step_index: i,
    step_id: s.id,
    method: s.method,
    path: s.path,
    status_code: 200,
    duration_ms: 40 + i * 17,
    response_excerpt: '{"ok": true}',
    error: null,
  }));
  const run: WorkflowRun = {
    id: runId,
    workspace: m[1],
    workflow_id: wf.id,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    status: 'success',
    error: null,
    steps,
  };
  state3.runs.unshift(run);
  return run;
});

route('GET', /^\/workflows\/([^/]+)\/([^/]+)\/runs$/, ({ m }) => {
  const summaries: WorkflowRunSummary[] = state3.runs
    .filter((r) => r.workflow_id === m[2])
    .map((r) => ({
      id: r.id,
      ws_id: r.workspace,
      workflow_id: r.workflow_id,
      started_at: r.started_at,
      finished_at: r.finished_at,
      status: r.status,
      params: '{}',
      error: r.error,
    }));
  return summaries;
});

route('GET', /^\/workflows\/([^/]+)\/([^/]+)\/runs\/([^/]+)$/, ({ m }) => {
  const run = state3.runs.find((r) => r.workflow_id === m[2] && r.id === m[3]);
  if (!run) throw new HttpError(404, `unknown run ${m[3]}`);
  return run;
});


/* -------------------------------------------- "Mi dinero" money organizer */
/* The whole organizer is implemented in ./fixtures-organizer so the hub really behaves: marking a
   charge paid moves the dot, accepting a candidate creates a commitment, auto-planning
   fills the plan and bulk-labelling empties the uncategorized list. */

route('GET', /^\/organizer\/([^/]+)\/summary$/, () => orgSummary());

route('GET', /^\/organizer\/([^/]+)\/commitments$/, ({ url }) =>
  orgList(url.searchParams.get('kind'), url.searchParams.get('status')),
);

route('POST', /^\/organizer\/([^/]+)\/commitments$/, ({ body }) =>
  orgCreate(body as Parameters<typeof orgCreate>[0]),
);

route('GET', /^\/organizer\/([^/]+)\/commitments\/([^/]+)$/, ({ m }) => {
  const d = orgDetail(m[2]);
  if (!d) throw new HttpError(404, `No existe el compromiso ${m[2]}`);
  return d;
});

route('PUT', /^\/organizer\/([^/]+)\/commitments\/([^/]+)$/, ({ m, body }) => {
  const c = orgUpdate(m[2], body as Parameters<typeof orgUpdate>[1]);
  if (!c) throw new HttpError(404, `No existe el compromiso ${m[2]}`);
  return c;
});

route('DELETE', /^\/organizer\/([^/]+)\/commitments\/([^/]+)$/, ({ m }) => {
  orgSetStatus(m[2], 'cancelled');
  return { ok: true };
});

route('POST', /^\/organizer\/([^/]+)\/commitments\/([^/]+)\/pause$/, ({ m }) => orgSetStatus(m[2], 'paused'));
route('POST', /^\/organizer\/([^/]+)\/commitments\/([^/]+)\/resume$/, ({ m }) => orgSetStatus(m[2], 'active'));
route('POST', /^\/organizer\/([^/]+)\/commitments\/([^/]+)\/cancel$/, ({ m, body }) =>
  orgSetStatus(m[2], 'cancelled', (body as { cancel_notes?: string } | undefined)?.cancel_notes ?? null),
);

route('POST', /^\/organizer\/([^/]+)\/quickadd$/, ({ url, body }) =>
  orgQuickAdd(String((body as { text?: string } | undefined)?.text ?? ''), url.searchParams.get('save') === '1'),
);

route('POST', /^\/organizer\/([^/]+)\/detect$/, () => orgDetect());
/** Resumable: the same persisted candidates a `POST /detect` produced, `?status=` filterable. */
route('GET', /^\/organizer\/([^/]+)\/detect$/, ({ url }) => {
  const status = url.searchParams.get('status');
  const r = orgDetect();
  return status ? { ...r, candidates: r.candidates.filter((c) => c.status === status) } : r;
});
route('POST', /^\/organizer\/([^/]+)\/detect\/accept$/, ({ body }) => {
  const b = (body ?? {}) as { candidate_id?: string; overrides?: Record<string, unknown> };
  const c = orgAcceptCandidate(String(b.candidate_id), b.overrides as never);
  if (!c) throw new HttpError(404, 'Ese candidato ya no existe');
  return c;
});
route('POST', /^\/organizer\/([^/]+)\/detect\/dismiss$/, ({ body }) =>
  orgDismissCandidate(String((body as { candidate_id?: string } | undefined)?.candidate_id)),
);

route('GET', /^\/organizer\/([^/]+)\/alerts$/, () => orgAlerts());
route('POST', /^\/organizer\/([^/]+)\/alerts\/([^/]+)\/dismiss$/, ({ m }) => {
  ORG.dismissedAlerts.add(m[2]);
  return { ok: true };
});

route('GET', /^\/organizer\/([^/]+)\/calendar$/, ({ url }) => {
  const from = url.searchParams.get('from') ?? todayLocalIso().slice(0, 8) + '01';
  const to = url.searchParams.get('to') ?? from;
  return orgCalendar(from, to);
});

/** The body route; the legacy positional route below stays as an alias. */
route('POST', /^\/organizer\/([^/]+)\/occurrences\/mark$/, ({ body }) => {
  const b = (body ?? {}) as import('../types-organizer').MarkOccurrenceBody;
  if (!b.commitment_id) throw pydanticError(['body', 'commitment_id'], 'Field required', 'missing');
  if (!b.date) throw pydanticError(['body', 'date'], 'Field required', 'missing');
  if (b.status !== 'paid' && b.status !== 'skipped') {
    throw pydanticError(['body', 'status'], "Input should be 'paid' or 'skipped'", 'enum');
  }
  return orgMarkBody(b);
});
route('DELETE', /^\/organizer\/([^/]+)\/occurrences\/mark$/, ({ url }) => {
  const cid = url.searchParams.get('commitment_id') ?? '';
  const date = url.searchParams.get('date') ?? '';
  if (!cid) throw pydanticError(['query', 'commitment_id'], 'Field required', 'missing');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw pydanticError(['query', 'date'], 'Input should be a valid date');
  return orgUnmark(cid, date);
});
route('POST', /^\/organizer\/([^/]+)\/occurrences\/([^/]+)\/(\d{4}-\d{2}-\d{2})\/mark$/, ({ m, body }) => {
  const b = (body ?? {}) as { status?: string; txn_id?: string };
  if (b.status !== 'paid' && b.status !== 'skipped') {
    throw pydanticError(['body', 'status'], "Input should be 'paid' or 'skipped'", 'enum');
  }
  return orgMark(m[2], m[3], b.status, b.txn_id ?? null);
});
route('POST', /^\/organizer\/([^/]+)\/commitments\/([^/]+)\/review$/, ({ m }) => {
  const c = orgList().find((x) => x.id === m[2]);
  if (!c) throw new HttpError(404, `commitment ${m[2]} not found`);
  c.reviewed_at = new Date().toISOString();
  return { reviewed_at: c.reviewed_at };
});

route('GET', /^\/organizer\/([^/]+)\/forecast$/, ({ url }) =>
  orgForecast(Number(url.searchParams.get('days') ?? 90)),
);
// Same body/answer as aurum/organizer/router.py api_set_buffer: {buffer} in, {buffer, source} out.
route('PUT', /^\/organizer\/([^/]+)\/forecast\/buffer$/, ({ body }) => {
  const buffer = (body as { buffer?: string | null } | undefined)?.buffer;
  if (buffer === null || buffer === undefined || buffer === '') {
    ORG.buffer = '2000.00';
    return { buffer: amt(ORG.buffer), source: '10% × monthly_committed (default)' };
  }
  if (!/^\d+(\.\d+)?$/.test(buffer)) throw new MockHttpError(400, { detail: 'buffer must be a decimal string' });
  ORG.buffer = buffer;
  return { buffer: amt(ORG.buffer), source: 'organizer_settings.buffer' };
});

route('GET', /^\/organizer\/([^/]+)\/plan$/, () => orgPlan());
route('POST', /^\/organizer\/([^/]+)\/plan\/auto$/, ({ body }) =>
  orgAutoPlan(Number((body as { months?: number } | undefined)?.months ?? 3)),
);
route('PUT', /^\/organizer\/([^/]+)\/plan$/, ({ body }) =>
  orgPutPlan(((body as { items?: { label_id: string; planned: string }[] } | undefined)?.items ?? [])),
);

route('POST', /^\/organizer\/([^/]+)\/organize$/, ({ body }) =>
  orgOrganize(((body as { assign?: Parameters<typeof orgOrganize>[0] } | undefined)?.assign ?? [])),
);

route('GET', /^\/organizer\/([^/]+)\/rules$/, () => ORG.rules);
route('DELETE', /^\/organizer\/([^/]+)\/rules\/([^/]+)$/, ({ m }) => {
  ORG.rules = ORG.rules.filter((r) => r.id !== m[2]);
  return { ok: true };
});

route('GET', /^\/organizer\/([^/]+)\/setup\/status$/, () => orgSetupStatus());
route('POST', /^\/organizer\/([^/]+)\/setup\/run$/, ({ body }) =>
  orgSetupRun(Number((body as { months?: number } | undefined)?.months ?? 3)),
);

/* ------------------------------------------------------------------ driver */


/* ---------------------------------- personal: accounts, entries, income streams */
/* The whole personal side is implemented in ./fixtures-personal so the manual path really behaves:
   a new account is immediately pickable in Agregar, an expense really moves the balance, an
   edit really changes both, and a delete really takes it out of Movimientos. */

const entryBody = (body: unknown) => body as import('../types-personal').EntryInput;

/** `label_name` is filled from the live label list, which lives in this module's state. */
function withLabelNames(rows: import('../types-personal').Entry[]): import('../types-personal').Entry[] {
  return rows.map((r) => ({
    ...r,
    label_name: r.label_id ? (state.labels.find((l) => l.id === r.label_id)?.name ?? null) : null,
  }));
}

route('POST', /^\/pf\/([^/]+)\/accounts$/, ({ body }) =>
  pfCreateAccount(body as import('../types-personal').PfAccountInput),
);
route('PUT', /^\/pf\/([^/]+)\/accounts\/([^/]+)$/, ({ m, body }) =>
  pfUpdateAccount(m[2], (body ?? {}) as Partial<import('../types-personal').PfAccountInput>),
);
/** DELETE archives when only the opening exists, else 409 `{detail, hint:'archive'}`. */
route('DELETE', /^\/pf\/([^/]+)\/accounts\/([^/]+)$/, ({ m }) => pfDeleteAccount(m[2]));
route('POST', /^\/pf\/([^/]+)\/accounts\/([^/]+)\/adjust$/, ({ m, body }) =>
  pfAdjustAccount(m[2], body as import('../types-personal').PfAccountAdjust),
);

/** An income entry with an expense label (or vice versa) is a 400 with the API's text. */
function checkLabelKind(body: Partial<import('../types-personal').EntryInput>, kind: string | undefined): void {
  if (!body.label_id) return;
  const label = state.labels.find((l) => l.id === body.label_id);
  if (!label) throw new HttpError(404, `label ${body.label_id} not found`);
  const lk = label.kind ?? 'expense';
  if (kind === 'income' && lk === 'expense') throw new HttpError(400, 'Esa categoría es de gastos');
  if (kind === 'expense' && lk === 'income') throw new HttpError(400, 'Esa categoría es de ingresos');
}

route('GET', /^\/pf\/([^/]+)\/entries$/, ({ url }) => {
  const rawLimit = url.searchParams.get('limit');
  const page = pfListEntries({
    from: url.searchParams.get('from'),
    to: url.searchParams.get('to'),
    account_id: url.searchParams.get('account_id'),
    label_id: url.searchParams.get('label_id'),
    kind: url.searchParams.get('kind'),
    q: url.searchParams.get('q'),
    limit: rawLimit ? Number(rawLimit) : null,
    cursor: url.searchParams.get('cursor'),
  });
  return { ...page, entries: withLabelNames(page.entries) };
});
route('POST', /^\/pf\/([^/]+)\/entries\/bulk$/, ({ body }) => {
  const list = (asRecord(body).entries ?? []) as import('../types-personal').EntryInput[];
  list.forEach((b) => checkLabelKind(b, b.kind));
  return pfBulkEntries(list, 'import');
});
route('POST', /^\/pf\/([^/]+)\/entries$/, ({ body }) => {
  const b = entryBody(body);
  checkLabelKind(b, b?.kind);
  return withLabelNames([pfCreateEntry(b, 'manual')])[0];
});
route('PUT', /^\/pf\/([^/]+)\/entries\/([^/]+)$/, ({ m, body }) => {
  const b = (body ?? {}) as Partial<import('../types-personal').EntryInput>;
  const prev = PF5.entries.find((e) => e.id === m[2]);
  checkLabelKind(b, b.kind ?? prev?.kind);
  return withLabelNames([pfUpdateEntry(m[2], b)])[0];
});
route('DELETE', /^\/pf\/([^/]+)\/entries\/([^/]+)$/, ({ m }) => pfDeleteEntry(m[2]));

route('GET', /^\/pf\/([^/]+)\/income\/streams$/, () => pfListStreams());
route('POST', /^\/pf\/([^/]+)\/income\/streams$/, ({ body }) =>
  pfCreateStream(body as import('../types-personal').IncomeStreamInput),
);
route('GET', /^\/pf\/([^/]+)\/income\/streams\/([^/]+)\/history$/, ({ m }) => pfStreamHistory(m[2]));
route('PUT', /^\/pf\/([^/]+)\/income\/streams\/([^/]+)$/, ({ m, body }) =>
  pfUpdateStream(m[2], (body ?? {}) as Partial<import('../types-personal').IncomeStreamInput>),
);
route('DELETE', /^\/pf\/([^/]+)\/income\/streams\/([^/]+)$/, ({ m }) => pfDeleteStream(m[2]));

route('GET', /^\/pf\/([^/]+)\/onboarding$/, () => pfOnboarding(orgList(null, 'active').length));

/* ---------------------------------------------- core: ledger health, backups */

route('GET', /^\/ledger\/([^/]+)\/health$/, () => ({ txns: state.journal.length + PF5.entries.length, errors: [], error_count: 0 }));
route('POST', /^\/backup$/, () => ({
  path: `data/backups/aurum-${new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)}Z.zip`,
  size: 20480,
  sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
}));
route('GET', /^\/backups$/, () => []);
route('GET', /^\/workspaces\/([^/]+)\/movimientos\.csv$/, () => ({
  __text: '\ufeffFecha;Tipo;Monto;Moneda;Cuenta;Cuenta destino;Categoría;Comercio;Nota;Etiquetas;Origen\n',
  __type: 'text/csv; charset=utf-8',
}));

class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

let installed = false;

/**
 * Security-middleware simulations: `setMockSimulation('unauthorized')` makes every
 * request a 401 `{error:'unauthorized'}` (+ WWW-Authenticate), `'origin_not_allowed'` a 403
 * `{error}`; `null` restores normal service. `?mock=unauthorized` on the page URL sets it at
 * install time so ui-check / tests can exercise the banner without touching code.
 */
export type MockSimulation = 'unauthorized' | 'origin_not_allowed' | 'host_not_allowed' | 'rate_limited' | 'server' | null;
let simulation: MockSimulation = null;
export function setMockSimulation(mode: MockSimulation): void {
  simulation = mode;
}
export function getMockSimulation(): MockSimulation {
  return simulation;
}

function simulatedResponse(): Response | null {
  if (!simulation) return null;
  const json = (payload: unknown, status: number, headers: Record<string, string> = {}) =>
    new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json', ...headers } });
  switch (simulation) {
    case 'unauthorized':
      return json({ error: 'unauthorized', hint: 'Authorization: Bearer <token> or X-Aurum-Token' }, 401, { 'WWW-Authenticate': 'Bearer' });
    case 'origin_not_allowed':
      return json({ error: 'origin_not_allowed' }, 403);
    case 'host_not_allowed':
      return json({ error: 'host_not_allowed' }, 403);
    case 'rate_limited':
      return json({ error: 'rate_limited' }, 429);
    case 'server':
      return json({ detail: 'Internal Server Error' }, 500);
    default:
      return null;
  }
}

export function installMockApi(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  try {
    const wanted = new URLSearchParams(window.location.search).get('mock');
    if (wanted === 'unauthorized' || wanted === 'origin_not_allowed' || wanted === 'host_not_allowed' || wanted === 'rate_limited' || wanted === 'server') {
      simulation = wanted;
    }
  } catch {
    /* no window.location in some test setups */
  }

  const real = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const href = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, window.location.origin);
    if (!url.pathname.startsWith(API_BASE)) return real(input as RequestInfo, init);

    // `seg()` encodes every segment; the routes match the decoded path, as uvicorn would see it.
    const path = decodeURIComponent(url.pathname.slice(API_BASE.length)) || '/';
    const method = (init?.method ?? 'GET').toUpperCase();

    let body: unknown;
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }

    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });

    // A visible latency so loading states are real, not a flash.
    await new Promise((r) => setTimeout(r, 60));

    // Workspace ids must match the server rule, else 400 {error:'invalid_workspace_id'}.
    const wsMatch = path.match(/^\/(?:pf|organizer|ledger|ingest|insights|tax\/mx\/resico|tax\/us|workflows|reports|business|holdings|plan|creditreport|crossborder|satsync)\/([^/]+)/);
    if (wsMatch && !/^[a-z0-9][a-z0-9-]{1,40}$/.test(decodeURIComponent(wsMatch[1]))) {
      return json({ error: 'invalid_workspace_id' }, 400);
    }
    const simulated = simulatedResponse();
    if (simulated) return simulated;

    for (const r of R) {
      if (r.method !== method) continue;
      const m = path.match(r.pattern);
      if (!m) continue;
      try {
        const out = r.handler({ m, url, body, init });
        // A handler may answer with raw text (the report HTML endpoint does).
        if (out && typeof out === 'object' && '__text' in (out as Record<string, unknown>)) {
          const t = out as { __text: string; __type?: string };
          return new Response(t.__text, {
            status: 200,
            headers: { 'Content-Type': t.__type ?? 'text/plain; charset=utf-8' },
          });
        }
        return json(out);
      } catch (e) {
        if (e instanceof MockHttpError) return json(e.body, e.status);
        if (e instanceof HttpError) return json({ detail: e.message }, e.status);
        return json({ detail: e instanceof Error ? e.message : String(e) }, 500);
      }
    }
    return json({ detail: `Mock: no hay ruta para ${method} ${path}` }, 404);
  };

  console.info('[aurum] mock API installed — default workspace', PERSONAL_WS_ID, '(demos:', WS_ID, ')');
}
