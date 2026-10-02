'use client';

/**
 * Pieces shared by the Mi dinero tabs: cadence wording, weekday names in
 * Python's Monday=0 order, the sign presentation of an occurrence amount, and the one
 * mark-paid state machine that Resumen, the calendar and the agenda all drive.
 *
 * No money math: the only string work on an amount is prefixing the minus that makes an
 * outflow's sign explicit; every figure is the API's own decimal string.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAddEntry } from '@/components/AddEntry';
import { useToast } from '@/components/ui';
import { errorMessage, getCommitment, markOccurrence, unmarkOccurrence } from '@/lib/api';
import { useI18n, type MsgKey } from '@/lib/i18n';
import type { Amount } from '@/lib/types';
import type { Cadence, CommitmentKind, Occurrence, OccurrenceStatus } from '@/lib/types-organizer';
import type { Lang } from '@/lib/types';

/* ------------------------------------------------------------- dialogs --- */

/**
 * `false` on the first render, `true` right after mount. A `ui/Dialog` that is mounted already
 * open closes itself again under React's dev StrictMode (the doubled layout effect calls
 * `close()`, whose async `close` event reaches the listener registered by the second run), so
 * conditionally mounted dialogs open through this flag instead of `open={true}`.
 */
export function useOpenAfterMount(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(true);
  }, []);
  return open;
}

/* ------------------------------------------------------------ cadence ---- */

/** Python's `date.weekday()` order (Monday = 0). `2024-01-01` is a Monday in local time. */
export function weekdayName(pyIndex: number, lang: Lang, style: 'short' | 'long' = 'long'): string {
  const d = new Date(2024, 0, 1 + ((pyIndex % 7) + 7) % 7);
  try {
    return new Intl.DateTimeFormat(lang === 'es' ? 'es-MX' : 'en-US', { weekday: style }).format(d);
  } catch {
    return String(pyIndex);
  }
}

/** JS `getDay()` (Sunday = 0) → Python weekday (Monday = 0). */
export const jsToPyWeekday = (js: number): number => (js + 6) % 7;

export interface CadenceLike {
  cadence: Cadence;
  interval_days?: number | null;
  anchor_day?: number | null;
  weekday?: number | null;
}

const MONTH_CADENCES: readonly Cadence[] = ['monthly', 'bimonthly', 'quarterly', 'semiannual', 'annual'];
const WEEK_CADENCES: readonly Cadence[] = ['weekly', 'biweekly'];

export const isMonthCadence = (c: Cadence): boolean => MONTH_CADENCES.includes(c);
export const isWeekCadence = (c: Cadence): boolean => WEEK_CADENCES.includes(c);

/** "Cada mes el día 15" / "Cada 2 semanas lunes" / "Cada 45 días" — from `money.every.*`. */
export function cadenceText(
  t: (key: MsgKey, vars?: Record<string, string | number>) => string,
  c: CadenceLike,
  lang: Lang,
): string {
  const base =
    c.cadence === 'custom'
      ? t('money.every.custom', { n: c.interval_days ?? 0 })
      : t(`money.every.${c.cadence}` as MsgKey);
  if (isMonthCadence(c.cadence) && c.anchor_day) {
    return `${base} ${c.anchor_day === 31 ? t('money.every.last_day') : t('money.every.day', { n: c.anchor_day })}`;
  }
  if (isWeekCadence(c.cadence) && c.weekday != null) {
    return `${base} · ${weekdayName(c.weekday, lang)}`;
  }
  return base;
}

/* ------------------------------------------------------------- kinds ----- */

/** The six choices of the '¿Qué es?' control, in display order; anything else reads 'Otro'. */
export const KIND_OPTIONS: readonly { kind: CommitmentKind; key: MsgKey }[] = [
  { kind: 'subscription', key: 'money.f.what.subscription' },
  { kind: 'utility', key: 'money.f.what.utility' },
  { kind: 'rent', key: 'money.f.what.rent' },
  { kind: 'loan_payment', key: 'money.f.what.loan_payment' },
  { kind: 'insurance', key: 'money.f.what.insurance' },
  { kind: 'bill', key: 'money.f.what.bill' },
];

/* ------------------------------------------------------------- amounts --- */

/**
 * An occurrence amount with its sign made explicit for display: outflows get a leading minus
 * (the organizer returns them positive), income stays positive and renders with `sign="always"`.
 */
export function signedAmount(kind: CommitmentKind | 'income' | 'commitment' | null | undefined, a: Amount): Amount {
  if (kind === 'income') return a;
  const raw = a.amount.trim();
  if (raw.startsWith('-') || /^0+(\.0+)?$/.test(raw)) return a;
  return { ...a, amount: `-${raw}` };
}

export const isIncomeKind = (kind: string | null | undefined): boolean => kind === 'income';

/* -------------------------------------------------------- mark actions --- */

/** Everything the mark-paid machine needs about one occurrence, whichever list it came from. */
export interface OccTarget {
  commitment_id: string;
  due: string;
  name: string;
  amount: Amount;
  /** The commitment kind (`income` for income rows). */
  kind: CommitmentKind | null | undefined;
  status: OccurrenceStatus;
  amount_variable?: boolean | null;
  account_id?: string | null;
  label_id?: string | null;
  entry_id?: string | null;
}

export type OccAction = 'paid' | 'register' | 'arrived' | 'skip' | 'undo';

/** Which action a row offers: fixed → Pagado; variable → Registrar; income → Ya llegó. */
export function primaryAction(o: Pick<OccTarget, 'kind' | 'status' | 'amount_variable'>): OccAction | null {
  if (o.status === 'paid' || o.status === 'skipped') return 'undo';
  if (isIncomeKind(o.kind)) return 'arrived';
  // Absent → treat as variable (Registrar) as the defensive default.
  return o.amount_variable === false ? 'paid' : 'register';
}

export interface OccurrenceActions {
  /** `commitment_id|due` of the row a request is in flight for, else null. */
  busy: string | null;
  /** Local status overrides (row flips immediately, reverts on error). */
  overrides: Record<string, OccurrenceStatus>;
  run: (action: OccAction, o: OccTarget) => void;
  /** Drop every override — the parent calls it once fresh rows have landed. */
  reset: () => void;
}

export const occKey = (o: Pick<OccTarget, 'commitment_id' | 'due'>): string => `${o.commitment_id}|${o.due}`;

/**
 * Whether the mark on `o` created its entry (`auto_created`), read from `GET /commitments/{id}`
 * whose occurrences carry the flag (the summary and calendar rows do not). `null` when the
 * occurrence is outside the detail's window or the request fails.
 */
async function autoCreated(ws: string, o: Pick<OccTarget, 'commitment_id' | 'due'>): Promise<boolean | null> {
  try {
    const detail = await getCommitment(ws, o.commitment_id);
    const occ = (detail.occurrences ?? []).find((x) => x.due === o.due) as (Occurrence & { auto_created?: boolean }) | undefined;
    return occ && typeof occ.auto_created === 'boolean' ? occ.auto_created : null;
  } catch {
    return null;
  }
}

/**
 * The mark-paid state machine shared by every list: flips the row locally, calls the API,
 * toasts with Deshacer (except after Registrar, whose movement undo cannot void), and asks the
 * parent to reload. `onDone` is called after every
 * successful write; `onStatus` receives a one-line result for in-dialog `role="status"` lines.
 */
export function useOccurrenceActions(
  ws: string,
  opts: { onDone: () => void; onStatus?: (text: string) => void },
): OccurrenceActions {
  const { t } = useI18n();
  const toast = useToast();
  const { open } = useAddEntry();
  const [busy, setBusy] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, OccurrenceStatus>>({});
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const flip = useCallback((o: OccTarget, status: OccurrenceStatus | null) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (status === null) delete next[occKey(o)];
      else next[occKey(o)] = status;
      return next;
    });
  }, []);

  const undo = useCallback(
    async (o: OccTarget) => {
      const key = occKey(o);
      setBusy(key);
      try {
        // A paid mark that links a movement the user logged (Registrar, or a matched one) cannot
        // be undone from here: `DELETE /occurrences/mark` only voids auto-created entries, the
        // user's entry keeps its `commitment_id` and the organizer re-matches it, so the row is
        // 'Pagado' again after the reload. Ask the detail (its occurrences carry `auto_created`)
        // before touching anything; when it cannot tell, the DELETE response decides.
        let kept = o.status === 'paid' && !!o.entry_id && (await autoCreated(ws, o)) === false;
        if (!kept) {
          flip(o, o.status === 'paid' || o.status === 'skipped' ? 'upcoming' : o.status);
          const res = await unmarkOccurrence(ws, o.commitment_id, o.due);
          kept = o.status === 'paid' && !!o.entry_id && !res.voided_entry_id;
          if (kept) flip(o, null);
        }
        const message = kept ? t('money.toast.kept') : t('money.toast.undone');
        optsRef.current.onStatus?.(message);
        if (kept) toast.info(message);
        else toast.success(message);
        optsRef.current.onDone();
      } catch (e) {
        flip(o, null);
        toast.error(errorMessage(e, t));
      } finally {
        setBusy(null);
      }
    },
    [ws, t, toast, flip],
  );

  const mark = useCallback(
    async (o: OccTarget, status: 'paid' | 'skipped', entryId?: string) => {
      const key = occKey(o);
      setBusy(key);
      flip(o, status);
      const income = isIncomeKind(o.kind);
      const message =
        status === 'skipped'
          ? t('money.toast.skipped')
          : entryId
            ? t('money.toast.registered')
            : income
              ? t('money.toast.arrived')
              : t('money.toast.paid');
      try {
        const res = await markOccurrence(ws, {
          commitment_id: o.commitment_id,
          date: o.due,
          status,
          ...(entryId ? { entry_id: entryId } : { log_entry: status === 'paid' }),
        });
        optsRef.current.onStatus?.(message);
        // Registrar links the user's own movement, which undo cannot void (see `undo`): that
        // toast carries no Deshacer. Every other success toast does.
        const undone: OccTarget = { ...o, status, entry_id: res.entry_id ?? entryId ?? o.entry_id ?? null };
        toast.success(message, entryId ? undefined : { action: { label: t('common.undo'), onClick: () => void undo(undone) } });
        optsRef.current.onDone();
      } catch (e) {
        flip(o, null);
        toast.error(errorMessage(e, t));
      } finally {
        setBusy(null);
      }
    },
    [ws, t, toast, flip, undo],
  );

  const register = useCallback(
    (o: OccTarget) => {
      open({
        kind: isIncomeKind(o.kind) ? 'income' : 'expense',
        accountId: o.account_id ?? undefined,
        prefill: {
          amount: { amount: o.amount.amount.replace(/^-/, ''), currency: o.amount.currency },
          payee: o.name,
          date: o.due,
          label_id: o.label_id ?? null,
          commitment_id: o.commitment_id,
        },
        onSaved: (entry) => void mark(o, 'paid', entry.id),
      });
    },
    [open, mark],
  );

  const run = useCallback(
    (action: OccAction, o: OccTarget) => {
      if (busy) return;
      switch (action) {
        case 'paid':
        case 'arrived':
          void mark(o, 'paid');
          return;
        case 'skip':
          void mark(o, 'skipped');
          return;
        case 'register':
          register(o);
          return;
        case 'undo':
          void undo(o);
          return;
        default:
          return;
      }
    },
    [busy, mark, register, undo],
  );

  const reset = useCallback(() => setOverrides({}), []);

  return { busy, overrides, run, reset };
}

/** The label of an action button. */
export function actionLabel(t: (key: MsgKey) => string, action: OccAction): string {
  switch (action) {
    case 'paid':
      return t('money.action.paid');
    case 'register':
      return t('money.action.register');
    case 'arrived':
      return t('money.action.arrived');
    case 'skip':
      return t('money.occ.skip');
    default:
      return t('common.undo');
  }
}

/** Badge tone for an occurrence status. */
export function statusTone(status: OccurrenceStatus): 'neutral' | 'pos' | 'neg' | 'warn' | 'info' {
  switch (status) {
    case 'paid':
      return 'pos';
    case 'missed':
      return 'neg';
    case 'due':
      return 'warn';
    case 'skipped':
      return 'neutral';
    default:
      return 'info';
  }
}
