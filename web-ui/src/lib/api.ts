/**
 * The one typed client for the Aurum API. Every endpoint the UI uses has exactly
 * one function here; no component calls `fetch` directly.
 *
 * Base URL: `NEXT_PUBLIC_API_URL`, default `/api` (same origin — the nginx image in
 * ./Dockerfile proxies `/api` to `${API_URL}`, which compose sets to http://api:5041).
 *
 * With `NEXT_PUBLIC_MOCK=1` the first call lazily imports `./mock`, which patches
 * `window.fetch`. The mock therefore lives in its own chunk and never ships in a real build.
 *
 * Response shapes below match the REAL API — captured live in `web-ui/docs/api-samples.json` —
 * not guessed envelopes. Most list endpoints return a bare array; only
 * `budgets/status`, `pf/accounts`, `pf/income`, `pf/review`, `pf/recurring`, tax month-close and
 * amortization/whatif/projection responses come back as objects.
 */
import { es as DATA_ES } from './i18n/data';
import type {
  AccountsOverview,
  Amortization,
  Amount,
  BackupEntry,
  BackupResult,
  Balances,
  Budget,
  BudgetInput,
  BudgetsCopyResult,
  BudgetsStatus,
  Budgets,
  Cards,
  CfdiDirection,
  CreditCardInput,
  CreditScoreInput,
  CreditScores,
  CfdiList,
  CfdiTipo,
  ChangesResponse,
  LawChange,
  Goal,
  GoalCreate,
  GoalInput,
  GoalProjection,
  Goals,
  GoalWhatIf,
  Health,
  IncomeOverview,
  InboxItem,
  InboxList,
  InboxStatus,
  Journal,
  Jurisdiction,
  Label,
  LabelCreate,
  LabelInput,
  LabelKind,
  LabelPatch,
  Labels,
  LedgerAccounts,
  LedgerHealth,
  Lang,
  Loans,
  LoanInput,
  LoanWhatIf,
  MsiInput,
  MetodoPago,
  MonthClose,
  MonthlyReview,
  QueryRows,
  RecurringOverview,
  ResearchAnswer,
  ReconcileBoard,
  RuleResult,
  Rules,
  Statement,
  StatementType,
  SyncJobs,
  Transaction,
  TransactionResult,
  UploadResult,
  VaultStatus,
  Workspace,
  WorkspaceInput,
  CreditReportImport,
  CreditReportState,
  CrossborderAssessment,
  CrossborderProfile,
  CrossborderProfileSaved,
  Explain,
  FxRate,
  HoldingsOverview,
  MonteCarloResult,
  PriceInput,
  RefsGraph,
  SavedScenario,
  ScenarioInputs,
  ScenarioRun,
  ScenarioSpec,
  SensitivityResult,
  TradeInput,
  TradeResult,
  TxFranchise,
  UsTaxYear,
  WatchProposal,
  WatchSource,
  WatchSourceHistory,
} from './types';
import type {
  Commitment,
  CommitmentDetail,
  CommitmentInput,
  CommitmentKind,
  CommitmentPatch,
  MarkOccurrenceBody,
  MarkOccurrenceResult,
  UnmarkOccurrenceResult,
  CommitmentStatus,
  DetectResult,
  Forecast,
  OkResult,
  OrgAlert,
  OrganizeAssignment,
  OrganizeResult,
  OrganizerCalendar,
  OrganizerPlan,
  OrganizerRule,
  OrganizerSummary,
  OccurrenceStatus,
  QuickAddPreview,
  SetupRunResult,
  SetupStatus,
} from './types-organizer';
import type {
  ArchivedReport,
  BizConstants,
  BusinessKpis,
  CalendarEntry,
  Digest,
  Employee,
  Insight,
  InvoiceRegister,
  InvoiceReminder,
  PayrollRun,
  PayrollRunSummary,
  ReportCatalog,
  ReportPreview,
  WorkflowCatalog,
  WorkflowDetail,
  WorkflowProposal,
  WorkflowRun,
  WorkflowRunSummary,
  WorkflowScheduleResult,
  WorkflowSummary,
} from './types-business';
import type {
  BankCsvResult,
  BulkCreateResult,
  EntriesPage,
  Entry,
  EntryInput,
  EntryQuery,
  EntryVoidResult,
  IncomeStream,
  IncomeStreamInput,
  Onboarding,
  PfAccount,
  PfAccountAdjust,
  PfAccountInput,
  QuickAddResult,
  ReceiptScan,
  StreamHistory,
  StreamHistoryRow,
} from './types-personal';

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '/api').replace(/\/$/, '');
export const MOCK_ENABLED = process.env.NEXT_PUBLIC_MOCK === '1';

/* =========================================================== request layer */
/*
 * How a request goes out and what an error carries:
 *
 *   - every path segment goes through `seg()` (encodeURIComponent);
 *   - every request appends `lang=<requestLang>` unless the path has one;
 *   - a manual AbortController timeout (15 s, 60 s for multipart) — never
 *     `AbortSignal.timeout`, which jsdom lacks — merged with an optional caller signal;
 *   - an empty / 204 body resolves `undefined` (never `res.json()` on it);
 *   - `ApiError` carries `{status, code, field, message, detail}` so screens can say what to
 *     do instead of echoing server text; `errorMessage(e, t)` turns the code into copy.
 */

/** `encodeURIComponent` on one path segment — ids and workspace names are user-typed. */
export const seg = (v: string | number): string => encodeURIComponent(String(v));

let requestLang: Lang | null = null;

/**
 * The language every request carries as `?lang=`. The I18nProvider calls
 * this when the user toggles; until it does, the stored preference (`aurum.lang`) is used so
 * the first requests already match the language the provider will apply after mount.
 */
export function setRequestLang(lang: Lang): void {
  requestLang = lang;
}

export function getRequestLang(): Lang {
  if (requestLang) return requestLang;
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem('aurum.lang');
      if (stored === 'en' || stored === 'es') return stored;
    } catch {
      /* storage blocked */
    }
  }
  return 'es';
}

const TIMEOUT_ENV = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS);
/** JSON requests: 15 s unless `NEXT_PUBLIC_API_TIMEOUT_MS` says otherwise. */
export const REQUEST_TIMEOUT_MS = Number.isFinite(TIMEOUT_ENV) && TIMEOUT_ENV > 0 ? TIMEOUT_ENV : 15_000;
/** Multipart uploads (CSV, CFDI zips): 60 s, or the override when it is longer. */
export const UPLOAD_TIMEOUT_MS = Math.max(60_000, REQUEST_TIMEOUT_MS);

/** Machine-readable reasons a request failed. Screens key copy off these, never off text. */
export type ApiErrorCode =
  | 'network'
  | 'timeout'
  | 'unauthorized'
  | 'origin_not_allowed'
  | 'host_not_allowed'
  | 'demo_mode_read_only'
  | 'bad_path'
  | 'invalid_workspace_id'
  | 'payload_too_large'
  | 'rate_limited'
  | 'validation'
  | 'server'
  | 'conflict'
  | 'not_found'
  | 'budget_exists'
  | 'account_has_movements'
  | 'entry_already_deleted'
  | 'splits_sum'
  | 'transfer_same_account'
  | 'transfer_needs_target'
  | 'account_archived'
  | 'amount_not_positive'
  | 'entry_not_editable'
  | 'duplicate'
  | (string & {});

/** Typed error carrying the API's `detail` (FastAPI's shape), the HTTP status and a code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: ApiErrorCode;
  /** For `validation`: the offending field (`loc` minus the leading body/query/path). */
  readonly field?: string;
  /** The raw body (`detail` or the whole `{error}` object) for callers that need more. */
  readonly detail: unknown;

  constructor(
    message: string,
    status: number,
    opts: { code?: ApiErrorCode; field?: string; detail?: unknown } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = opts.code;
    this.field = opts.field;
    this.detail = opts.detail;
  }
}

/** The ordered regex table for string `detail`s the personal endpoints still raise as text. */
const DETAIL_CODES: [RegExp, ApiErrorCode][] = [
  [/already exists|ya existe.*presupuesto|budget.*(exists|duplicate)|UNIQUE.*budget/i, 'budget_exists'],
  [/has movements|tiene movimientos|archive it instead/i, 'account_has_movements'],
  [/already deleted|was deleted|ya estaba borrado|ya fue borrado/i, 'entry_already_deleted'],
  [/splits? must sum|partes deben sumar|do not sum/i, 'splits_sum'],
  [/same account|misma cuenta|to_account_id.*(equal|same|itself)|cannot transfer to itself/i, 'transfer_same_account'],
  [/transfer requires to_account_id|needs? (a )?target|cuenta destino/i, 'transfer_needs_target'],
  [/is archived|está archivada|archived account/i, 'account_archived'],
  [/must be (positive|> ?0|greater than (zero|0))|mayor que cero|amount_not_positive/i, 'amount_not_positive'],
  [/not editable|no se edita|non_editable|source:/i, 'entry_not_editable'],
];

interface PydanticItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

const LOC_PREFIXES = new Set(['body', 'query', 'path', 'header']);

function fieldFromLoc(loc: (string | number)[] | undefined): string | undefined {
  if (!Array.isArray(loc) || loc.length === 0) return undefined;
  const parts = loc.map(String);
  if (parts.length > 1 && LOC_PREFIXES.has(parts[0])) parts.shift();
  return parts.join('.') || undefined;
}

/**
 * Map an HTTP failure into an `ApiError`. Pure, so the tests can pin every branch:
 * pydantic arrays → `validation`; `{detail:{code}}` → that code; `{error}` middleware bodies →
 * that string; string `detail`s → the regex table, then 409/404; 5xx → `server`.
 */
export function mapApiError(status: number, body: unknown, statusText = ''): ApiError {
  const b = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>;
  const detail = 'detail' in b ? b.detail : undefined;

  // pydantic 422 (and the security middleware's `{"error":"validation","detail":[…]}`)
  if (Array.isArray(detail)) {
    const first = (detail[0] ?? {}) as PydanticItem;
    const msg = typeof first.msg === 'string' ? first.msg : statusText || 'validation';
    return new ApiError(msg, status, { code: 'validation', field: fieldFromLoc(first.loc), detail });
  }

  // Coded detail objects (`{code, message, field}` / organizer `{code:'duplicate'}`
  // / bulk `{index, msg}`).
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === 'string' ? (d.code as ApiErrorCode) : undefined;
    const message =
      (typeof d.message === 'string' && d.message) ||
      (typeof d.msg === 'string' && d.msg) ||
      (typeof d.detail === 'string' && d.detail) ||
      code ||
      statusText ||
      `HTTP ${status}`;
    const field =
      typeof d.field === 'string' ? d.field : typeof d.index === 'number' ? `entries.${d.index}` : undefined;
    return new ApiError(message, status, {
      code: code ?? (typeof d.index === 'number' ? 'validation' : statusCode(status)),
      field,
      detail,
    });
  }

  // Middleware bodies: `{"error": "<code>", "hint"?, "message"?}`.
  if (typeof b.error === 'string' && b.error) {
    const message =
      (typeof b.message === 'string' && b.message) || (typeof b.hint === 'string' && b.hint) || b.error;
    return new ApiError(message, status, { code: b.error as ApiErrorCode, detail: b });
  }

  if (typeof detail === 'string' && detail) {
    const hit = DETAIL_CODES.find(([re]) => re.test(detail));
    return new ApiError(detail, status, { code: hit ? hit[1] : statusCode(status), detail });
  }

  const message = (typeof b.message === 'string' && b.message) || statusText || `HTTP ${status}`;
  return new ApiError(message, status, { code: statusCode(status), detail: body });
}

function statusCode(status: number): ApiErrorCode | undefined {
  if (status >= 500) return 'server';
  if (status === 401) return 'unauthorized';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 413) return 'payload_too_large';
  if (status === 429) return 'rate_limited';
  if (status === 422 || status === 400) return 'validation';
  return undefined;
}

/* ------------------------------------------------------- error copy (err.*) */

type Vars = Record<string, string | number>;
/** Any `t` — a plain `(key) => string` or the provider's `(key, vars) => string`. */
type Translate<K extends string> = (key: K, vars?: Vars) => string;

/** `code → err.* key` where they differ (403 shapes). */
const CODE_KEYS: Record<string, string> = {
  origin_not_allowed: 'err.forbidden.origin',
  host_not_allowed: 'err.forbidden.origin',
  demo_mode_read_only: 'err.forbidden.demo',
  forbidden: 'err.forbidden.demo',
  invalid_workspace_id: 'err.bad_path',
  duplicate: 'err.conflict',
};

/** The `err.*` key an error maps to, or `err.generic` when the code has no copy. */
export function errorKey(e: unknown): string {
  const code = e instanceof ApiError ? e.code : e instanceof Error && e.name === 'AbortError' ? 'timeout' : undefined;
  if (!code) return 'err.generic';
  const key = CODE_KEYS[code] ?? `err.${code}`;
  return key in DATA_ES ? key : 'err.generic';
}

function interpolate(template: string, vars: Vars): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

function fieldLabel<K extends string>(field: string | undefined, t?: Translate<K>): string {
  if (!field) return '';
  const last = field.split('.').pop() ?? field;
  const key = `err.field.${last}`;
  if (key in DATA_ES) return t ? t(key as K) : DATA_ES[key as keyof typeof DATA_ES];
  return last.replace(/_/g, ' ');
}

/**
 * Human copy for any thrown value. With `t` (the I18n hook) the copy follows the UI language;
 * without it (legacy one-arg callers) the Spanish table in `i18n/data.ts` is used, so the
 * ~25 `errorMessage(e)` call sites keep working unchanged.
 */
export function errorMessage<K extends string = string>(e: unknown, t?: Translate<K>): string {
  const key = errorKey(e);
  const serverText = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
  const vars: Vars = { message: serverText };
  if (e instanceof ApiError) {
    if (e.field) vars.field = fieldLabel(e.field, t);
    if (e.code === 'entry_not_editable') {
      const m = /source:\s*([a-z_]+)/i.exec(serverText);
      vars.source = m ? m[1] : serverText;
    }
  }
  if (key === 'err.validation' && !vars.field) vars.field = fieldLabel('generic', t);
  const raw = t ? t(key as K, vars) : DATA_ES[key as keyof typeof DATA_ES];
  // A `t` without `vars` support returns the template verbatim, so interpolate here too.
  return interpolate(raw ?? serverText, vars);
}

/* ------------------------------------------------------- 401 registries */

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
const okListeners = new Set<Listener>();
let lastUnauthorizedAt = 0;
let sawUnauthorized = false;

/** Called at most once per 2 s when any request answers 401. Returns the unsubscribe. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

/** Called on the first 2xx after a 401 (the HealthProvider clears its flag). */
export function onRequestOk(listener: Listener): () => void {
  okListeners.add(listener);
  return () => {
    okListeners.delete(listener);
  };
}

function noteUnauthorized(): void {
  sawUnauthorized = true;
  const now = Date.now();
  if (now - lastUnauthorizedAt < 2_000) return;
  lastUnauthorizedAt = now;
  for (const l of unauthorizedListeners) l();
}

function noteOk(): void {
  if (!sawUnauthorized) return;
  sawUnauthorized = false;
  for (const l of okListeners) l();
}

/** Test hook: forget the throttle window and the "saw a 401" flag. */
export function _resetAuthState(): void {
  lastUnauthorizedAt = 0;
  sawUnauthorized = false;
}

let mockReady: Promise<void> | null = null;
async function ensureMock(): Promise<void> {
  if (!MOCK_ENABLED || typeof window === 'undefined') return;
  if (!mockReady) mockReady = import('./mock').then((m) => m.installMockApi());
  return mockReady;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/* ------------------------------------------------------------ bearer token */
/**
 * The API may require a token (`Authorization: Bearer`, also accepted as
 * `X-Aurum-Token`). It is a local secret typed by the user in Ajustes and kept in
 * `localStorage` under `aurum.token` — never sent anywhere but the API base URL, never
 * logged. The legacy key `aurum.api_token` is read once and migrated.
 */
const TOKEN_KEY = 'aurum.token';
const LEGACY_TOKEN_KEY = 'aurum.api_token';

export function getApiToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    const current = window.localStorage.getItem(TOKEN_KEY);
    if (current !== null) return current;
    const legacy = window.localStorage.getItem(LEGACY_TOKEN_KEY);
    if (legacy !== null) {
      window.localStorage.removeItem(LEGACY_TOKEN_KEY);
      if (legacy) window.localStorage.setItem(TOKEN_KEY, legacy);
      return legacy;
    }
    return '';
  } catch {
    return '';
  }
}

export function setApiToken(token: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* storage blocked — the token simply does not persist */
  }
}

function authHeaders(): Record<string, string> {
  const token = getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/* ----------------------------------------------------------------- request */

export interface RequestOptions {
  /** A caller's own abort signal (useResource passes one); merged with the timeout. */
  signal?: AbortSignal | null;
  /** Override the timeout for one call (ms). */
  timeoutMs?: number;
}

function withLang(path: string): string {
  if (/[?&]lang=/.test(path)) return path;
  return `${path}${path.includes('?') ? '&' : '?'}lang=${getRequestLang()}`;
}

/** Fetch + parse with the timeout/abort/lang/auth rules above; resolves the parsed body. */
async function fetchApi(
  path: string,
  init: RequestInit | undefined,
  opts: RequestOptions,
  accept: string,
  parse: (res: Response) => Promise<unknown>,
): Promise<unknown> {
  await ensureMock();
  const isForm = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  const timeoutMs = opts.timeoutMs ?? (isForm ? UPLOAD_TIMEOUT_MS : REQUEST_TIMEOUT_MS);

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const outer = opts.signal;
  const onOuterAbort = () => controller.abort();
  if (outer) {
    if (outer.aborted) controller.abort();
    else outer.addEventListener('abort', onOuterAbort, { once: true });
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${withLang(path)}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: accept,
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        ...authHeaders(),
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onOuterAbort);
    if (timedOut) throw new ApiError('timeout', 0, { code: 'timeout', detail: e });
    if (e instanceof Error && e.name === 'AbortError') throw e; // the caller cancelled
    throw new ApiError(e instanceof Error ? e.message : String(e), 0, { code: 'network', detail: e });
  }
  clearTimeout(timer);
  outer?.removeEventListener('abort', onOuterAbort);

  if (!res.ok) {
    let body: unknown;
    try {
      const text = await res.text();
      body = text ? JSON.parse(text) : undefined;
    } catch {
      body = undefined;
    }
    const err = mapApiError(res.status, body, res.statusText);
    if (res.status === 401) noteUnauthorized();
    throw err;
  }
  noteOk();
  return parse(res);
}

async function parseJson(res: Response): Promise<unknown> {
  if (res.status === 204) return undefined;
  const text = await res.text();
  if (!text) return undefined;
  return JSON.parse(text) as unknown;
}

async function request<T>(path: string, init?: RequestInit, opts: RequestOptions = {}): Promise<T> {
  return (await fetchApi(path, init, opts, 'application/json', parseJson)) as T;
}

/** Same as `request`, for endpoints that answer with text (digest, report HTML). */
async function requestText(path: string, opts: RequestOptions = {}): Promise<string> {
  return (await fetchApi(path, undefined, opts, 'text/plain, text/html, */*', (res) => res.text())) as string;
}

const get = <T,>(path: string, opts?: RequestOptions) => request<T>(path, undefined, opts);
const post = <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }, opts);
const postForm = <T,>(path: string, form: FormData, opts?: RequestOptions) =>
  request<T>(path, { method: 'POST', body: form }, opts);
const put = <T,>(path: string, body?: unknown, opts?: RequestOptions) =>
  request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) }, opts);
const del = <T,>(path: string, opts?: RequestOptions) => request<T>(path, { method: 'DELETE' }, opts);

/* --------------------------------------------------------------------- core */

export const getHealth = () => get<Health>('/health');
/** GET /api/workspaces — ordered personal-first; hidden ones only with `includeHidden`. */
export const listWorkspaces = (opts: { includeHidden?: boolean } = {}) =>
  get<Workspace[]>(`/workspaces${qs({ include_hidden: opts.includeHidden ? 1 : undefined })}`);
export const getWorkspace = (ws: string) => get<Workspace>(`/workspaces/${seg(ws)}`);
export const createWorkspace = (body: WorkspaceInput) => post<Workspace>('/workspaces', body);
/** PUT /api/workspaces/{ws} — id is immutable. */
export const updateWorkspace = (ws: string, body: Partial<WorkspaceInput> & { hidden?: boolean }) =>
  put<Workspace>(`/workspaces/${seg(ws)}`, body);

/** GET /api/workspaces/{ws}/backup.zip — a download, so the UI links straight at it. */
export const backupUrl = (ws: string) => `${API_BASE}/workspaces/${seg(ws)}/backup.zip`;
/** GET /api/workspaces/{ws}/movimientos.csv?from&to — UTF-8 BOM, `;` separated. */
export const movimientosCsvUrl = (ws: string, from?: string, to?: string) =>
  `${API_BASE}/workspaces/${seg(ws)}/movimientos.csv${qs({ from, to })}`;
/** POST /api/backup — full data backup on the server side. */
export const createBackup = () => post<BackupResult>('/backup');
export const listBackups = () => get<BackupEntry[]>('/backups');
export const backupDownloadUrl = (name: string) => `${API_BASE}/backups/${seg(name)}`;
/** GET /api/ledger/{ws}/health — parse errors of the workspace ledger. */
export const getLedgerHealth = (ws: string) => get<LedgerHealth>(`/ledger/${seg(ws)}/health`);

/* ------------------------------------------------------------------- ledger */

export const getJournal = (
  ws: string,
  opts: { start?: string; end?: string; account_prefix?: string } = {},
) => get<Journal>(`/ledger/${seg(ws)}/journal${qs(opts)}`);

export const getBalances = (ws: string, as_of?: string) =>
  get<Balances>(`/ledger/${seg(ws)}/balances${qs({ as_of })}`);

export const getLedgerAccounts = (ws: string) => get<LedgerAccounts>(`/ledger/${seg(ws)}/accounts`);

export const runQuery = (ws: string, bql: string) =>
  post<QueryRows>(`/ledger/${seg(ws)}/query`, { bql });

/** POST /api/ledger/{ws}/transactions — body is a `Transaction`. */
export const createTransaction = (ws: string, txn: Transaction) =>
  post<TransactionResult>(`/ledger/${seg(ws)}/transactions`, txn);
/** PUT — rewrites the transaction with that link. */
export const updateTransaction = (ws: string, txnId: string, txn: Transaction) =>
  put<TransactionResult>(`/ledger/${seg(ws)}/transactions/${seg(txnId)}`, txn);
/** DELETE — tags `#voided` and books a reversing entry; history is never erased. */
export const voidTransaction = (ws: string, txnId: string) =>
  del<TransactionResult>(`/ledger/${seg(ws)}/transactions/${seg(txnId)}`);

/** GET /api/ledger/{ws}/statements/{period}?type= */
export const getStatement = (ws: string, period: string, type: StatementType) =>
  get<Statement>(`/ledger/${seg(ws)}/statements/${seg(period)}${qs({ type })}`);

/* -------------------------------------------------------------------- rules */

export const listRules = () => get<Rules>('/rules');
export const computeRule = (id: string, inputs: Record<string, unknown>) =>
  post<RuleResult>(`/rules/${seg(id)}/compute`, inputs);

/* ---------------------------------------------------------------------- tax */

export const getMonthClose = (ws: string, period: string) =>
  get<MonthClose>(`/tax/mx/resico/${seg(ws)}/${seg(period)}`);

/** Not fetched: it is a file download, so the UI links straight at it. */
export const draftPdfUrl = (ws: string, period: string) =>
  `${API_BASE}/tax/mx/resico/${seg(ws)}/${seg(period)}/draft.pdf`;

/* ------------------------------------------------------------------- ingest */

export const listCfdi = (
  ws: string,
  opts: {
    period?: string;
    tipo?: CfdiTipo;
    metodo_pago?: MetodoPago;
    direction?: CfdiDirection;
  } = {},
) => get<CfdiList>(`/ingest/${seg(ws)}/cfdi${qs(opts)}`);

export function uploadCfdi(ws: string, files: File[]): Promise<UploadResult> {
  const form = new FormData();
  for (const f of files) form.append('files', f, f.name);
  return postForm<UploadResult>(`/ingest/${seg(ws)}/cfdi`, form);
}

/**
 * POST /api/ingest/{ws}/bank/csv (multipart) — `account_id` is required and the rows are
 * written as pf entries (source `import`, deduplicated).
 */
/**
 * POST /api/ingest/{ws}/receipts (multipart) — keep a receipt photo, read it and get a
 * suggestion for + Agregar. Nothing is saved as a movement; the movement's `attachment` points here.
 */
export function scanReceipt(ws: string, file: File, opts?: RequestOptions): Promise<ReceiptScan> {
  const form = new FormData();
  form.append('file', file, file.name || 'recibo.jpg');
  return postForm<ReceiptScan>(`/ingest/${seg(ws)}/receipts`, form, opts);
}

/**
 * The stored receipt photo as an object URL. Fetched through the request layer (auth header, timeout)
 * because an `<img src>` could not send the bearer token; the caller revokes it.
 */
export async function receiptObjectUrl(ws: string, id: string): Promise<string> {
  const blob = (await fetchApi(
    `/ingest/${seg(ws)}/receipts/${seg(id)}/image`,
    undefined,
    {},
    'image/*',
    (res) => res.blob(),
  )) as Blob;
  return URL.createObjectURL(blob);
}

export function importBankCsv(ws: string, file: File, accountId: string, bank?: string): Promise<BankCsvResult> {
  const form = new FormData();
  form.append('file', file, file.name);
  form.append('account_id', accountId);
  if (bank) form.append('bank', bank);
  return postForm<BankCsvResult>(`/ingest/${seg(ws)}/bank/csv`, form);
}

/** @deprecated old signature (no account) — use `importBankCsv(ws, file, accountId, bank)`. */
export function uploadBankCsv(ws: string, file: File, bank: string): Promise<UploadResult> {
  const form = new FormData();
  form.append('file', file, file.name);
  form.append('bank', bank);
  return postForm<UploadResult>(`/ingest/${seg(ws)}/bank/csv`, form);
}

/** POST /api/ingest/{ws}/quickadd — a parsed preview, no inbox row; `commit` writes an entry. */
export const quickAddPreview = (ws: string, text: string, accountId?: string | null) =>
  post<QuickAddResult>(`/ingest/${seg(ws)}/quickadd`, {
    text,
    ...(accountId ? { account_id: accountId } : {}),
  });
export const quickAddCommit = (ws: string, text: string, accountId?: string | null) =>
  post<QuickAddResult>(`/ingest/${seg(ws)}/quickadd`, {
    text,
    commit: true,
    ...(accountId ? { account_id: accountId } : {}),
  });
/** @deprecated old inbox shape — use `quickAddPreview` / `quickAddCommit`. */
export const quickAdd = (ws: string, text: string) =>
  post<InboxItem>(`/ingest/${seg(ws)}/quickadd`, { text });

/** GET /api/ingest/{ws}/reconcile?period= */
export const getReconcile = (ws: string, period: string) =>
  get<ReconcileBoard>(`/ingest/${seg(ws)}/reconcile${qs({ period })}`);

export const matchBankLine = (
  ws: string,
  body: { bank_line_id: string; txn_id?: string; cfdi_uuid?: string },
) => post<ReconcileBoard>(`/ingest/${seg(ws)}/reconcile/match`, body);

export const unmatchBankLine = (ws: string, bankLineId: string) =>
  post<ReconcileBoard>(`/ingest/${seg(ws)}/reconcile/unmatch`, { bank_line_id: bankLineId });

export const listInbox = (ws: string, status: InboxStatus | 'all' = 'pending') =>
  get<InboxList>(`/ingest/${seg(ws)}/inbox${qs({ status: status === 'all' ? undefined : status })}`);

export const acceptInbox = (
  ws: string,
  id: string,
  overrides?: { label?: string; account?: string },
) => post<InboxItem>(`/ingest/${seg(ws)}/inbox/${seg(id)}/accept`, overrides ?? {});

export const rejectInbox = (ws: string, id: string) =>
  post<InboxItem>(`/ingest/${seg(ws)}/inbox/${seg(id)}/reject`);

/* ------------------------------------------------------------------ satsync */

export const getVaultStatus = (ws: string) => get<VaultStatus>(`/satsync/${seg(ws)}/vault`);
export const listSyncJobs = (ws: string) => get<SyncJobs>(`/satsync/${seg(ws)}/jobs`);

/* ----------------------------------------------------------------------- pf */

export const getAccountsOverview = (ws: string) => get<AccountsOverview>(`/pf/${seg(ws)}/accounts`);
export const getIncome = (ws: string, months = 3) =>
  get<IncomeOverview>(`/pf/${seg(ws)}/income${qs({ months })}`);
/** GET /pf/{ws}/labels?kind=&include_archived=. The old `listLabels(ws)` still works. */
export const listLabels = (ws: string, opts: { kind?: LabelKind; includeArchived?: boolean } = {}) =>
  get<Labels>(
    `/pf/${seg(ws)}/labels${qs({ kind: opts.kind, include_archived: opts.includeArchived ? 1 : undefined })}`,
  );
export const saveLabel = (ws: string, label: Label) => post<Label>(`/pf/${seg(ws)}/labels`, label);
/** POST /labels — `{name, kind, parent?, icon?, aliases?}`; the legacy full `LabelInput` still posts. */
export const createLabel = (ws: string, body: LabelCreate | LabelInput) =>
  post<Label>(`/pf/${seg(ws)}/labels`, body);
export const updateLabel = (ws: string, id: string, body: LabelPatch | LabelInput) =>
  put<Label>(`/pf/${seg(ws)}/labels/${seg(id)}`, body);
export const deleteLabel = (ws: string, id: string) => del<{ ok: boolean }>(`/pf/${seg(ws)}/labels/${seg(id)}`);
export const listBudgets = (ws: string, period?: string) =>
  get<Budgets>(`/pf/${seg(ws)}/budgets${qs({ period })}`);
/** @deprecated use `listBudgets`. */
export const getBudgets = listBudgets;
export const getBudgetStatus = (ws: string, period: string) =>
  get<BudgetsStatus>(`/pf/${seg(ws)}/budgets/status${qs({ period })}`);
/** @deprecated use `getBudgetStatus`. */
export const getBudgetsStatus = getBudgetStatus;
/** POST /budgets/copy {from,to} — idempotent ("Copiar del mes anterior"). */
export const copyBudgets = (ws: string, from: string, to: string) =>
  post<BudgetsCopyResult>(`/pf/${seg(ws)}/budgets/copy`, { from, to });
export const createBudget = (ws: string, body: BudgetInput) => post<Budget>(`/pf/${seg(ws)}/budgets`, body);
export const updateBudget = (ws: string, id: string, body: BudgetInput) =>
  put<Budget>(`/pf/${seg(ws)}/budgets/${seg(id)}`, body);
export const deleteBudget = (ws: string, id: string) => del<{ ok: boolean }>(`/pf/${seg(ws)}/budgets/${seg(id)}`);
export const listGoals = (ws: string) => get<Goals>(`/pf/${seg(ws)}/goals`);
/** @deprecated use `listGoals`. */
export const getGoals = listGoals;
/** POST /goals — `account_id` preferred; the legacy `GoalInput` (ledger `account`) still posts. */
export const createGoal = (ws: string, body: GoalCreate | GoalInput) => post<Goal>(`/pf/${seg(ws)}/goals`, body);
export const updateGoal = (ws: string, id: string, body: Partial<GoalCreate> | GoalInput) =>
  put<Goal>(`/pf/${seg(ws)}/goals/${seg(id)}`, body);
export const deleteGoal = (ws: string, id: string) => del<{ ok: boolean }>(`/pf/${seg(ws)}/goals/${seg(id)}`);
/** `extra_monthly` is a decimal string (aurum/pf/goals.py WhatIf) — the API does the math. */
export const goalWhatIf = (ws: string, id: string, extraMonthly: string) =>
  post<GoalWhatIf>(`/pf/${seg(ws)}/goals/${seg(id)}/whatif`, { extra_monthly: extraMonthly });
/** @deprecated use `goalWhatIf`. */
export const getGoalWhatIf = goalWhatIf;
export const getGoalProjection = (ws: string, goalId: string) =>
  get<GoalProjection>(`/pf/${seg(ws)}/goals/${seg(goalId)}/projection`);
export const getCards = (ws: string) => get<Cards>(`/pf/${seg(ws)}/credit/cards`);
export const createCard = (ws: string, body: CreditCardInput) =>
  post<CreditCardInput>(`/pf/${seg(ws)}/credit/cards`, body);
export const createMsi = (ws: string, cardId: string, body: MsiInput) =>
  post<MsiInput>(`/pf/${seg(ws)}/credit/cards/${seg(cardId)}/msi`, body);
export const getLoans = (ws: string) => get<Loans>(`/pf/${seg(ws)}/credit/loans`);
export const createLoan = (ws: string, body: LoanInput) => post<LoanInput>(`/pf/${seg(ws)}/credit/loans`, body);
export const listScores = (ws: string) => get<CreditScores>(`/pf/${seg(ws)}/credit/scores`);
export const createScore = (ws: string, body: CreditScoreInput) =>
  post<CreditScoreInput>(`/pf/${seg(ws)}/credit/scores`, body);
export const deleteScore = (ws: string, id: string) =>
  del<{ ok: boolean }>(`/pf/${seg(ws)}/credit/scores/${seg(id)}`);
export const getAmortization = (ws: string, loanId: string, extra?: string) =>
  get<Amortization>(`/pf/${seg(ws)}/credit/loans/${seg(loanId)}/amortization${qs({ extra })}`);
/** `extra_payment` is a decimal string (never a float) — the API does the arithmetic. */
export const getLoanWhatIf = (ws: string, loanId: string, extraPayment: string) =>
  post<LoanWhatIf>(`/pf/${seg(ws)}/credit/loans/${seg(loanId)}/whatif`, { extra_payment: extraPayment });
export const getReview = (ws: string, period: string) =>
  get<MonthlyReview>(`/pf/${seg(ws)}/review/${seg(period)}`);
export const getRecurring = (ws: string) => get<RecurringOverview>(`/pf/${seg(ws)}/recurring`);

/* ---------------------------------------------------------- research / watch */
/* Endpoints below are not covered by api-samples.json; request/response shapes are
   assumed, not yet checked against the real API. */

/** not yet checked against a real API response */
export const ask = (body: {
  question: string;
  jurisdiction: Jurisdiction | 'both';
  lang: Lang;
  workspace?: string | null;
  /** Restrict the corpus to what was in force on this date. */
  as_of?: string | null;
}) => post<ResearchAnswer>('/research/ask', body);

/** not yet checked against a real API response */
export const getChanges = (since?: string) => get<LawChange[]>(`/watch/changes${qs({ since })}`);
/** not yet checked against a real API response */
export const runWatch = () => post<ChangesResponse>('/watch/run');

/* ============================= US tax, cross-border, holdings, plan, watch */
/* Shapes below are the ones captured live in docs/api-samples.json.        */

/* --------------------------------------------------------- tax/us + xborder */

export const getUsTax = (ws: string, year: number) => get<UsTaxYear>(`/tax/us/${seg(ws)}/${seg(year)}`);
export const getTxFranchise = (ws: string, year: number) =>
  get<TxFranchise>(`/tax/us/${seg(ws)}/${seg(year)}/tx-franchise`);
/** A file download, so the UI links straight at it (DRAFT organizer, never a return). */
export const organizerPdfUrl = (ws: string, year: number) =>
  `${API_BASE}/tax/us/${seg(ws)}/${seg(year)}/organizer.pdf`;

export const getCrossborder = (ws: string) =>
  get<CrossborderAssessment>(`/crossborder/${seg(ws)}/assessment`);
export const putCrossborderProfile = (ws: string, body: CrossborderProfile) =>
  put<CrossborderProfileSaved>(`/crossborder/${seg(ws)}/profile`, body);

/* ----------------------------------------------------------- holdings / fx */

export const getHoldings = (ws: string) => get<HoldingsOverview>(`/holdings/${seg(ws)}`);
export const createTrade = (ws: string, body: TradeInput) =>
  post<TradeResult>(`/holdings/${seg(ws)}/trades`, body);
export const createPrice = (ws: string, body: PriceInput) =>
  post<{ symbol: string; date: string }>(`/holdings/${seg(ws)}/prices`, body);

/** 404 when there is no Banxico token and no fixture — callers show a "no rate" state. */
export const getFxRate = (base: string, quote: string, date?: string) =>
  get<FxRate>(`/fx/rate${qs({ base, quote, date })}`);

/* ------------------------------------------------------------ creditreport */

export const getCreditReport = (ws: string) => get<CreditReportState>(`/creditreport/${seg(ws)}`);
export const getCreditReportExplain = (ws: string) => get<Explain>(`/creditreport/${seg(ws)}/explain`);
export function importCreditReport(ws: string, file: File): Promise<CreditReportImport> {
  const form = new FormData();
  form.append('file', file, file.name);
  return postForm<CreditReportImport>(`/creditreport/${seg(ws)}/import`, form);
}

/* --------------------------------------------------------------------- plan */

export const listScenarios = (ws: string) => get<ScenarioSpec[]>(`/plan/${seg(ws)}/scenarios`);
export const runScenario = (ws: string, id: string, inputs: ScenarioInputs) =>
  post<ScenarioRun>(`/plan/${seg(ws)}/scenarios/${seg(id)}/run`, inputs);
export const runSensitivity = (
  ws: string,
  id: string,
  body: { inputs: ScenarioInputs; vary: string[]; range_pct: number },
) => post<SensitivityResult>(`/plan/${seg(ws)}/scenarios/${seg(id)}/sensitivity`, body);
export const runMonteCarlo = (
  ws: string,
  id: string,
  body: { inputs: ScenarioInputs; n: number; seed: number },
) => post<MonteCarloResult>(`/plan/${seg(ws)}/scenarios/${seg(id)}/montecarlo`, body);
export const listSavedScenarios = (ws: string) => get<SavedScenario[]>(`/plan/${seg(ws)}/saved`);
export const saveScenario = (
  ws: string,
  body: { scenario_id: string; name: string; inputs: ScenarioInputs },
) => post<SavedScenario>(`/plan/${seg(ws)}/saved`, body);
export const deleteSavedScenario = (ws: string, id: string) =>
  del<{ ok: boolean }>(`/plan/${seg(ws)}/saved/${seg(id)}`);

/* ---------------------------------------------------------- research / watch */

export const getRefs = (law: string, article: string) =>
  get<RefsGraph>(`/research/refs${qs({ law, article })}`);

export const listWatchSources = () => get<WatchSource[]>('/watch/sources');
export const getWatchSourceHistory = (id: string) =>
  get<WatchSourceHistory>(`/watch/sources/${seg(id)}/history`);
export const listWatchProposals = () => get<WatchProposal[]>('/watch/proposals');

/* =================================================== business, insights, reports */
/* Shapes captured live in docs/api-samples.json (business / insights / reports). */


/* ------------------------------------------------------------- business */

export const getBusinessKpis = (ws: string, period: string, currency?: string) =>
  get<BusinessKpis>(`/business/${seg(ws)}/kpis${qs({ period, currency })}`);

export const getInvoiceRegister = (
  ws: string,
  opts: { period?: string; start?: string; end?: string; as_of?: string; currency?: string } = {},
) => get<InvoiceRegister>(`/business/${seg(ws)}/invoices${qs(opts)}`);

/** Returns reminder *text* for the user to send. Aurum never sends a message itself. */
export const getInvoiceReminder = (ws: string, uuid: string, clientName?: string) =>
  post<InvoiceReminder>(`/business/${seg(ws)}/invoices/remind`, {
    uuid,
    ...(clientName ? { client_name: clientName } : {}),
  });

export const listEmployees = (ws: string, activeOnly = true) =>
  get<Employee[]>(`/business/${seg(ws)}/payroll/employees${qs({ active_only: activeOnly })}`);

export const listPayrollRuns = (ws: string, period?: string) =>
  get<PayrollRunSummary[]>(`/business/${seg(ws)}/payroll${qs({ period })}`);

export const runPayroll = (
  ws: string,
  body: { period: string; days?: string; post?: boolean; lang?: Lang },
) => post<PayrollRun>(`/business/${seg(ws)}/payroll/run`, body);

export const getPayrollRun = (ws: string, runId: string) =>
  get<PayrollRun>(`/business/${seg(ws)}/payroll/${seg(runId)}`);

/** A file download (watermarked DRAFT), so the UI links straight at it. */
export const payrollDraftPdfUrl = (ws: string, runId: string) =>
  `${API_BASE}/business/${seg(ws)}/payroll/${seg(runId)}/draft.pdf`;

export const getBusinessConstants = () => get<BizConstants>('/business/constants/mx-nl');

/* ------------------------------------------------------------- insights */

export const listInsights = (ws: string, opts: { period?: string; lang?: Lang } = {}) =>
  get<Insight[]>(`/insights/${seg(ws)}${qs(opts)}`);

export const dismissInsight = (ws: string, id: string) =>
  post<{ ok: boolean; ws_id: string; insight_id: string }>(`/insights/${seg(ws)}/${seg(id)}/dismiss`);

export const getInsightCalendar = (ws: string, from: string, to: string) =>
  get<CalendarEntry[]>(`/insights/${seg(ws)}/calendar${qs({ from, to })}`);

/** `format=json` so the digest arrives with its counts; the plain text is `.text`. */
export const getDigest = (ws: string, opts: { period?: string; lang?: Lang } = {}) =>
  get<Digest>(`/insights/${seg(ws)}/digest${qs({ ...opts, format: 'json' })}`);

/* -------------------------------------------------------------- reports */

export const getReportCatalog = (ws: string) => get<ReportCatalog>(`/reports/${seg(ws)}`);

export const getReportPreview = (ws: string, pack: string, opts: { period?: string; lang?: Lang } = {}) =>
  get<ReportPreview>(`/reports/${seg(ws)}/${seg(pack)}/preview${qs(opts)}`);

export const getReportHtml = (ws: string, pack: string, opts: { period?: string; lang?: Lang } = {}) =>
  requestText(`/reports/${seg(ws)}/${seg(pack)}${qs({ ...opts, format: 'html' })}`);

/** A file download, so the UI links straight at it. */
export const reportPdfUrl = (ws: string, pack: string, opts: { period?: string; lang?: Lang } = {}) =>
  `${API_BASE}/reports/${seg(ws)}/${seg(pack)}${qs({ ...opts, format: 'pdf' })}`;

export const archiveReport = (
  ws: string,
  pack: string,
  opts: { period?: string; lang?: Lang; format?: 'pdf' | 'html' } = {},
) => post<ArchivedReport>(`/reports/${seg(ws)}/${seg(pack)}/archive${qs(opts)}`);

/** 404 when the pack has never been archived — callers render the empty state. */
export const listArchivedReports = (ws: string, pack: string) =>
  get<ArchivedReport[]>(`/reports/${seg(ws)}/${seg(pack)}/archive`);

/* =============================================================== workflows */
/* Verified against the real API (2026-09). GET /{ws} is a bare summary list; the yaml and
   parsed definition only come back from the per-workflow detail endpoint. */

export const listWorkflows = (ws: string) => get<WorkflowSummary[]>(`/workflows/${seg(ws)}`);
export const getWorkflow = (ws: string, id: string) => get<WorkflowDetail>(`/workflows/${seg(ws)}/${seg(id)}`);
export const createWorkflow = (ws: string, body: { yaml: string }) =>
  post<WorkflowDetail>(`/workflows/${seg(ws)}`, body);
export const updateWorkflow = (ws: string, id: string, body: { yaml: string }) =>
  put<WorkflowDetail>(`/workflows/${seg(ws)}/${seg(id)}`, body);
export const deleteWorkflow = (ws: string, id: string) => del<unknown>(`/workflows/${seg(ws)}/${seg(id)}`);
export const runWorkflow = (ws: string, id: string, params: Record<string, unknown> = {}) =>
  post<WorkflowRun>(`/workflows/${seg(ws)}/${seg(id)}/run`, { params });
export const listWorkflowRuns = (ws: string, id: string) =>
  get<WorkflowRunSummary[]>(`/workflows/${seg(ws)}/${seg(id)}/runs`);
export const getWorkflowRun = (ws: string, id: string, runId: string) =>
  get<WorkflowRun>(`/workflows/${seg(ws)}/${seg(id)}/runs/${seg(runId)}`);
export const scheduleWorkflow = (ws: string, id: string, cron: string | null) =>
  post<WorkflowScheduleResult>(`/workflows/${seg(ws)}/${seg(id)}/schedule`, { cron });
export const deleteWorkflowSchedule = (ws: string, id: string) =>
  del<WorkflowScheduleResult>(`/workflows/${seg(ws)}/${seg(id)}/schedule`);
/** An LLM draft. Never auto-saved, never auto-run. */
export const proposeWorkflow = (ws: string, description: string) =>
  post<WorkflowProposal>(`/workflows/${seg(ws)}/propose`, { description });
export const getWorkflowCatalog = () => get<WorkflowCatalog>('/workflows/catalog');

/* ================================================== "Mi dinero" organizer */
/* Every organizer endpoint. List endpoints are
   bare arrays, matching the rest of this API; each response can carry an `explain`. */

export const getOrganizerSummary = (ws: string) =>
  get<OrganizerSummary>(`/organizer/${seg(ws)}/summary`);

export const listCommitments = (
  ws: string,
  opts: { kind?: CommitmentKind; status?: CommitmentStatus } = {},
) => get<Commitment[]>(`/organizer/${seg(ws)}/commitments${qs(opts)}`);

export const getCommitment = (ws: string, id: string) =>
  get<CommitmentDetail>(`/organizer/${seg(ws)}/commitments/${seg(id)}`);

export const createCommitment = (ws: string, body: CommitmentInput) =>
  post<Commitment>(`/organizer/${seg(ws)}/commitments`, body);

/** PUT /commitments/{id} = PATCH-merge: unset fields stay untouched. */
export const patchCommitment = (ws: string, id: string, body: CommitmentPatch) =>
  put<Commitment>(`/organizer/${seg(ws)}/commitments/${seg(id)}`, body);
/** @deprecated use `patchCommitment`. */
export const updateCommitment = patchCommitment;
/** POST /commitments/{id}/review → `{reviewed_at}`. */
export const reviewCommitment = (ws: string, id: string) =>
  post<{ reviewed_at: string }>(`/organizer/${seg(ws)}/commitments/${seg(id)}/review`);

/** Soft delete: the API sets status `cancelled` and stamps `ended`. */
export const deleteCommitment = (ws: string, id: string) =>
  del<unknown>(`/organizer/${seg(ws)}/commitments/${seg(id)}`);

export const pauseCommitment = (ws: string, id: string) =>
  post<Commitment>(`/organizer/${seg(ws)}/commitments/${seg(id)}/pause`);

export const resumeCommitment = (ws: string, id: string) =>
  post<Commitment>(`/organizer/${seg(ws)}/commitments/${seg(id)}/resume`);

/** Cancelling asks for the checklist note, which the API stores as `cancel_notes`. */
export const cancelCommitment = (ws: string, id: string, cancel_notes?: string) =>
  post<Commitment>(`/organizer/${seg(ws)}/commitments/${seg(id)}/cancel`, { cancel_notes: cancel_notes ?? null });

/** One line in ("netflix 219 mensual día 15"), a parsed preview out. `save` persists it. */
export const organizerQuickAdd = (ws: string, text: string, save = false) =>
  post<QuickAddPreview>(`/organizer/${seg(ws)}/quickadd${qs({ save: save ? 1 : undefined })}`, { text });

export const runDetect = (ws: string) => post<DetectResult>(`/organizer/${seg(ws)}/detect`);

/** The persisted candidates from a previous `runDetect` — lets the setup wizard resume. */
export const getDetectCandidates = (ws: string, status?: string) =>
  get<DetectResult>(`/organizer/${seg(ws)}/detect${qs({ status })}`);

export const acceptCandidate = (ws: string, candidate_id: string, overrides?: Partial<CommitmentInput>) =>
  post<Commitment>(`/organizer/${seg(ws)}/detect/accept`, { candidate_id, ...(overrides ? { overrides } : {}) });

export const dismissCandidate = (ws: string, candidate_id: string) =>
  post<OkResult>(`/organizer/${seg(ws)}/detect/dismiss`, { candidate_id });

export const getAlerts = (ws: string) => get<OrgAlert[]>(`/organizer/${seg(ws)}/alerts`);
/** @deprecated use `getAlerts`. */
export const listOrganizerAlerts = getAlerts;

export const dismissAlert = (ws: string, id: string) =>
  post<OkResult>(`/organizer/${seg(ws)}/alerts/${seg(id)}/dismiss`);
/** @deprecated use `dismissAlert`. */
export const dismissOrganizerAlert = dismissAlert;

export const getOrganizerCalendar = (ws: string, from: string, to: string) =>
  get<OrganizerCalendar>(`/organizer/${seg(ws)}/calendar${qs({ from, to })}`);

/**
 * POST /organizer/{ws}/occurrences/mark. The body form is the current one; the positional
 * form `(ws, commitmentId, due, status, txn_id?)` is kept for MoneyCalendar and builds the same
 * body (`txn_id` travels as `entry_id`).
 */
export function markOccurrence(ws: string, body: MarkOccurrenceBody): Promise<MarkOccurrenceResult>;
export function markOccurrence(
  ws: string,
  commitmentId: string,
  due: string,
  status: Extract<OccurrenceStatus, 'paid' | 'skipped'>,
  txn_id?: string,
): Promise<MarkOccurrenceResult>;
export function markOccurrence(
  ws: string,
  bodyOrId: MarkOccurrenceBody | string,
  due?: string,
  status?: Extract<OccurrenceStatus, 'paid' | 'skipped'>,
  txn_id?: string,
): Promise<MarkOccurrenceResult> {
  const body: MarkOccurrenceBody =
    typeof bodyOrId === 'string'
      ? { commitment_id: bodyOrId, date: due ?? '', status: status ?? 'paid', ...(txn_id ? { entry_id: txn_id } : {}) }
      : bodyOrId;
  return post<MarkOccurrenceResult>(`/organizer/${seg(ws)}/occurrences/mark`, body);
}

/** DELETE /organizer/{ws}/occurrences/mark?commitment_id=&date= — un-marks (voids an auto-created entry). */
export const unmarkOccurrence = (ws: string, commitmentId: string, date: string) =>
  del<UnmarkOccurrenceResult>(`/organizer/${seg(ws)}/occurrences/mark${qs({ commitment_id: commitmentId, date })}`);

export const getForecast = (ws: string, days = 90) =>
  get<Forecast>(`/organizer/${seg(ws)}/forecast${qs({ days })}`);

/** PUT /organizer/{ws}/forecast/buffer — body `{buffer}` (decimal string, `null` = back to the default); returns the effective buffer + its formula. */
export const setForecastBuffer = (ws: string, buffer: string | null) =>
  put<{ buffer: Amount; source: string }>(`/organizer/${seg(ws)}/forecast/buffer`, { buffer });

export const getOrganizerPlan = (ws: string, period?: string) =>
  get<OrganizerPlan>(`/organizer/${seg(ws)}/plan${qs({ period })}`);

export const autoPlan = (ws: string, months = 3) =>
  post<OrganizerPlan>(`/organizer/${seg(ws)}/plan/auto`, { months });

export const putOrganizerPlan = (ws: string, items: { label_id: string; planned: string }[]) =>
  put<OrganizerPlan>(`/organizer/${seg(ws)}/plan`, { items });

/** Bulk-label the uncategorized list, optionally teaching a rule for next time. */
export const organizeTxns = (ws: string, assign: OrganizeAssignment[]) =>
  post<OrganizeResult>(`/organizer/${seg(ws)}/organize`, { assign });

export const listOrganizerRules = (ws: string) => get<OrganizerRule[]>(`/organizer/${seg(ws)}/rules`);

export const deleteOrganizerRule = (ws: string, id: string) =>
  del<unknown>(`/organizer/${seg(ws)}/rules/${seg(id)}`);

export const getSetupStatus = (ws: string) => get<SetupStatus>(`/organizer/${seg(ws)}/setup/status`);

export const runSetup = (ws: string, months = 3) =>
  post<SetupRunResult>(`/organizer/${seg(ws)}/setup/run`, { months });

/* =============================================================== personal pf */
/**
 * The manual-first personal endpoints. List readers stay defensive about a bare array vs an
 * envelope so an older server still renders; the current shapes (entries envelope, liability
 * sign, label kinds, onboarding ids) are the ones typed and the ones the mock serves.
 */

/** A list endpoint may answer with `[...]` (house style) or `{key: [...]}`. Accept both. */
function asList<T>(raw: unknown, key: string): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object') {
    const v = (raw as Record<string, unknown>)[key];
    if (Array.isArray(v)) return v as T[];
  }
  return [];
}

/**
 * `GET /pf/{ws}/accounts` keeps its original shape (groups/net worth/explain) and carries the
 * friendly `accounts` rows (balance positive-owed for liabilities, `balance_signed`,
 * `owed`). Older servers send only the former, so `accounts` is optional.
 */
export type PfAccountsResponse = AccountsOverview & { accounts?: PfAccount[] };

export const listPfAccounts = async (
  ws: string,
  opts: { includeArchived?: boolean } = {},
  reqOpts?: RequestOptions,
): Promise<PfAccount[]> => {
  const r = await get<PfAccountsResponse>(
    `/pf/${seg(ws)}/accounts${qs({ include_archived: opts.includeArchived ? 1 : undefined })}`,
    reqOpts,
  );
  return asList<PfAccount>(r?.accounts ?? r, 'accounts');
};

export const createPfAccount = (ws: string, body: PfAccountInput) =>
  post<PfAccount>(`/pf/${seg(ws)}/accounts`, body);

/** PUT /accounts/{id} — partial, including `archived` both ways. */
export const updatePfAccount = (ws: string, id: string, body: Partial<PfAccountInput>) =>
  put<PfAccount>(`/pf/${seg(ws)}/accounts/${seg(id)}`, body);

/** DELETE → archives when only opening/adjust txns exist, else 409 (`account_has_movements`). */
export const deletePfAccount = (ws: string, id: string) =>
  del<{ ok: boolean } | PfAccount | undefined>(`/pf/${seg(ws)}/accounts/${seg(id)}`);

/** POST /accounts/{id}/adjust — liabilities: what is owed, positive; the server posts the delta. */
export const adjustPfAccount = (ws: string, id: string, body: PfAccountAdjust) =>
  post<PfAccount>(`/pf/${seg(ws)}/accounts/${seg(id)}/adjust`, body);

const EMPTY_TOTALS = (currency: string): EntriesPage['totals'] => ({
  in: { amount: '0.00', currency },
  out: { amount: '0.00', currency },
  net: { amount: '0.00', currency },
  count: 0,
});

/**
 * GET /pf/{ws}/entries → `{entries, next_cursor, totals}`. An older server that
 * still answers a bare array is wrapped with zero totals so the page renders; the UI never
 * sums client-side.
 */
export const listEntries = async (
  ws: string,
  query: EntryQuery = {},
  reqOpts?: RequestOptions,
): Promise<EntriesPage> => {
  const r = await get<EntriesPage | Entry[]>(`/pf/${seg(ws)}/entries${qs({ ...query })}`, reqOpts);
  if (Array.isArray(r)) {
    return { entries: r, next_cursor: null, totals: EMPTY_TOTALS(r[0]?.amount.currency ?? 'MXN') };
  }
  return {
    entries: asList<Entry>(r, 'entries'),
    next_cursor: r?.next_cursor ?? null,
    totals: r?.totals ?? EMPTY_TOTALS('MXN'),
  };
};

export const createEntry = (ws: string, body: EntryInput) => post<Entry>(`/pf/${seg(ws)}/entries`, body);

/** PUT /entries/{id} — partial body; validate-then-write; missing txn → 409. */
export const updateEntry = (ws: string, id: string, body: Partial<EntryInput>) =>
  put<Entry>(`/pf/${seg(ws)}/entries/${seg(id)}`, body);

/** DELETE /entries/{id} → `{id, voided:true}`; a second delete → 409. */
export const deleteEntry = (ws: string, id: string) =>
  del<EntryVoidResult>(`/pf/${seg(ws)}/entries/${seg(id)}`);

/** POST /entries/bulk — all-or-nothing → `{created:[ids]}`. */
export const bulkCreateEntries = (ws: string, entries: EntryInput[]) =>
  post<BulkCreateResult>(`/pf/${seg(ws)}/entries/bulk`, { entries });

/** @deprecated old name; returned rows on older servers, `{created}` on the current one. */
export const createEntriesBulk = async (ws: string, entries: EntryInput[]): Promise<Entry[]> => {
  const r = await post<Entry[] | { entries?: Entry[]; created?: string[] }>(`/pf/${seg(ws)}/entries/bulk`, {
    entries,
  });
  return asList<Entry>(r, 'entries');
};

export const listStreams = async (ws: string, reqOpts?: RequestOptions): Promise<IncomeStream[]> => {
  const r = await get<IncomeStream[] | { streams?: IncomeStream[] }>(`/pf/${seg(ws)}/income/streams`, reqOpts);
  return asList<IncomeStream>(r, 'streams');
};
/** @deprecated use `listStreams`. */
export const listIncomeStreams = listStreams;

export const createStream = (ws: string, body: IncomeStreamInput) =>
  post<IncomeStream>(`/pf/${seg(ws)}/income/streams`, body);
/** @deprecated use `createStream`. */
export const createIncomeStream = createStream;

/** PUT /income/streams/{id} — partial merge, updated in place. */
export const updateStream = (ws: string, id: string, body: Partial<IncomeStreamInput>) =>
  put<IncomeStream>(`/pf/${seg(ws)}/income/streams/${seg(id)}`, body);
/** @deprecated use `updateStream`. */
export const updateIncomeStream = updateStream;

export const deleteStream = (ws: string, id: string) =>
  del<{ ok: boolean } | undefined>(`/pf/${seg(ws)}/income/streams/${seg(id)}`);
/** @deprecated use `deleteStream`. */
export const deleteIncomeStream = deleteStream;

/**
 * GET /income/streams/{id}/history — the server answers a bare array of occurrences
 * (`{due, expected, received, status}`, aurum/pf/streams.py); wrapped as `{stream_id, periods}`
 * for the existing consumer.
 */
export const getStreamHistory = async (ws: string, id: string, reqOpts?: RequestOptions): Promise<StreamHistory> => {
  const r = await get<StreamHistory | StreamHistoryRow[]>(`/pf/${seg(ws)}/income/streams/${seg(id)}/history`, reqOpts);
  const rows = asList<Partial<StreamHistoryRow> & { due?: string }>(r, 'periods').map((row) => ({
    due: row.due ?? (row.period ? `${row.period}-01` : ''),
    expected: row.expected ?? null,
    received: row.received ?? null,
    status: row.status ?? 'pending',
    period: row.period ?? (row.due ?? '').slice(0, 7),
    ...(row.count !== undefined ? { count: row.count } : {}),
  }));
  return { stream_id: id, periods: rows };
};

/** GET /pf/{ws}/onboarding → the step ids (`accounts, income, recurring, first_entries`). */
export const getOnboarding = (ws: string, reqOpts?: RequestOptions) =>
  get<Onboarding>(`/pf/${seg(ws)}/onboarding`, reqOpts);
