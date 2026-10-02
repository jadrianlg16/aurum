'use client';

/**
 * "+ Agregar" — the primary way to log money.
 *
 * One dialog, mounted once by `AddEntryProvider` in the shell and opened through
 * `useAddEntry().open(kindOrOpts, entry?)`: the header button, the FAB, every screen's own
 * "+ Agregar", the Movimientos row menu (edit / duplicate), Home's and Mi dinero's "Registrar"
 * (prefill + `commitment_id`) and the `?add=1` deep link all reuse it.
 *
 * Order inside: Gasto · Ingreso · Transferencia → Monto (focused) → Frecuentes chips + Categoría
 * → Cuenta (last used, or the only one) → Fecha (Hoy/Ayer) → "Más detalles" (comercio with the
 * recent payees, nota, etiquetas, dividir). Enter saves, Ctrl/Cmd+Enter saves and keeps the
 * dialog open for the next one, Esc cancels. After a save: toast "Guardado · −$250.00 · Comida
 * fuera · Deshacer" (undo = DELETE). Zero accounts → the account form takes the body. Edit mode
 * adds "Eliminar" behind a confirm with the formatted amount and date.
 *
 * On Gasto, "Leer foto del recibo (atajo)" (`movimientos/ReceiptScanner.tsx`) keeps a
 * photo, reads it and fills only the fields that are still empty (the date only while it is still
 * today's default); the movement carries the photo as `attachment`, and removing it in edit mode
 * sends `attachment: null`.
 *
 * The double entry is the API's job (`POST /pf/{ws}/entries` builds it): nothing in this file
 * mentions a posting, no amount is ever parsed to a number, and today's date is LOCAL.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { ApiError, createEntry, errorMessage, listEntries, listLabels, listPfAccounts, updateEntry } from '@/lib/api';
import { decimalSign, todayLocalIso } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Amount, Label } from '@/lib/types';
import type { Entry, EntryInput, EntryKind, PfAccount, ReceiptScan } from '@/lib/types-personal';
import { useAdvanced, useWorkspace } from '@/lib/workspace';
import { ISO_DATE_RE, isDecimalString, sumDecimals } from '@/lib/validate';
import { AccountForm } from './cuentas/AccountForm';
import { CategoryChips } from './movimientos/CategoryChips';
import { DeleteEntryDialog } from './movimientos/DeleteEntryDialog';
import { ReceiptScanner } from './movimientos/ReceiptScanner';
import { useEntryToast } from './movimientos/entryToast';
import styles from './movimientos/movimientos.module.css';
import { bumpCatUsage, readLastAccount, writeLastAccount } from './movimientos/prefs';
import { useOpenAfterMount } from './movimientos/useOpenAfterMount';
import {
  AccountPicker,
  Button,
  CategoryPicker,
  DateField,
  Dialog,
  Field,
  Input,
  Money,
  MoneyInput,
  Textarea,
  useToast,
} from './ui';

/* ------------------------------------------------------------------ context */

export type AddEntryMode = 'create' | 'edit' | 'duplicate';

/**
 * Object form of `open` (every personal screen uses it). The string form
 * `open('expense')` still works; `mode`/`entryId` are accepted so callers can type against the
 * full options shape, and `edit`/`duplicate` need the `Entry` as the second argument (there is no GET by id).
 * `prefill.amount` also accepts a bare decimal string (metas passes `monthly_required.amount`).
 */
export interface OpenAddEntryOptions {
  kind?: EntryKind;
  /** Wins over `prefill.account_id`. */
  accountId?: string;
  prefill?: Partial<Omit<EntryInput, 'amount'>> & { amount?: Amount | string | null; commitment_id?: string | null };
  mode?: AddEntryMode;
  /** Accepted, never fetched: the row itself must come as the second argument. */
  entryId?: string;
  /** Fires after every successful save with the row the API returned. */
  onSaved?: (entry: Entry) => void;
}

interface AddEntryValue {
  /** Open the dialog on a tab (string form) or with prefill/callbacks (object form). */
  open: (kindOrOpts?: EntryKind | OpenAddEntryOptions, entry?: Entry | null) => void;
  /** Bumped after every successful write, so lists can re-fetch by putting it in their deps. */
  version: number;
  /** Bump it by hand after a write made somewhere else (accounts, streams, undo). */
  bump: () => void;
}

const AddEntryContext = createContext<AddEntryValue | null>(null);

export function useAddEntry(): AddEntryValue {
  const ctx = useContext(AddEntryContext);
  // A screen rendered outside the shell (never happens in this app, but keep it honest)
  // simply gets a no-op opener rather than a crash.
  return ctx ?? { open: () => {}, version: 0, bump: () => {} };
}

type DialogState = { kind: EntryKind; mode: AddEntryMode; entry: Entry | null; opts: OpenAddEntryOptions };

/**
 * Owns the dialog and the "something changed" counter. Lives in the shell so the header
 * button and every screen share one dialog. The `n` shortcut lives in Shell.tsx; the provider
 * does not register it.
 */
export function AddEntryProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState | null>(null);
  const [version, setVersion] = useState(0);

  const value = useMemo<AddEntryValue>(
    () => ({
      open: (kindOrOpts = 'expense', entry = null) => {
        const opts: OpenAddEntryOptions = typeof kindOrOpts === 'string' ? { kind: kindOrOpts } : kindOrOpts;
        let mode: AddEntryMode = opts.mode ?? (entry ? 'edit' : 'create');
        if ((mode === 'edit' || mode === 'duplicate') && !entry) {
          if (process.env.NODE_ENV !== 'production') {
            console.warn(`useAddEntry().open: mode '${mode}' needs the Entry as the second argument; opening 'create'.`);
          }
          mode = 'create';
        }
        const kind = opts.kind ?? entry?.kind ?? opts.prefill?.kind ?? 'expense';
        // `duplicate` copies the row into a fresh movement dated today; `edit` keeps the row.
        const editing = mode === 'edit' ? entry : null;
        const prefill =
          mode === 'duplicate' && entry ? { ...entryToInput(entry), date: todayLocalIso(), ...opts.prefill } : opts.prefill;
        setState({ kind, mode, entry: editing, opts: { ...opts, kind, prefill } });
      },
      version,
      bump: () => setVersion((n) => n + 1),
    }),
    [version],
  );

  return (
    <AddEntryContext.Provider value={value}>
      {children}
      {state && (
        <AddEntryDialog
          kind={state.kind}
          mode={state.mode}
          entry={state.entry}
          prefill={state.opts.prefill}
          accountId={state.opts.accountId}
          onClose={(changed) => {
            setState(null);
            if (changed) setVersion((n) => n + 1);
          }}
          onSaved={(row) => {
            setVersion((n) => n + 1);
            state.opts.onSaved?.(row);
          }}
        />
      )}
    </AddEntryContext.Provider>
  );
}

/* ------------------------------------------------------------------- dialog */

const KINDS: EntryKind[] = ['expense', 'income', 'transfer'];
const PAYEE_LIMIT = 50;

/** The editable fields of a row, as the API would accept them back (used by `duplicate`). */
function entryToInput(e: Entry): OpenAddEntryOptions['prefill'] {
  return {
    kind: e.kind,
    date: e.date,
    amount: e.amount,
    // rows imported without an account (source cfdi/import) carry null; the picker then defaults
    account_id: e.account_id ?? undefined,
    to_account_id: e.to_account_id ?? null,
    label_id: e.label_id ?? null,
    payee: e.payee ?? null,
    note: e.note ?? null,
    tags: e.tags ?? [],
    splits: e.splits ?? null,
    // A duplicate is a NEW movement: the Mi dinero link of the original is not copied, otherwise
    // two rows would claim the same occurrence (callers that want it pass `prefill.commitment_id`).
  };
}

function unsigned(a: Amount | string | null | undefined): string {
  const raw = typeof a === 'string' ? a : a?.amount ?? '';
  return raw.trim().replace(/^[-−]/, '');
}

interface SplitRow {
  key: number;
  label_id: string;
  amount: string;
}

interface FieldErrors {
  amount?: string;
  date?: string;
  account?: string;
  to?: string;
  label?: string;
}

let splitSeq = 1;

export function AddEntryDialog({
  kind: initialKind,
  mode = 'create',
  entry,
  prefill,
  accountId: presetAccountId,
  onClose,
  onSaved,
}: {
  kind: EntryKind;
  mode?: AddEntryMode;
  entry: Entry | null;
  /** Seeds the fields (object form of `open`); `entry` fields win, then `prefill`, then defaults. */
  prefill?: OpenAddEntryOptions['prefill'];
  /** Wins over `prefill.account_id` and over the last-used / first-account default. */
  accountId?: string;
  /** `changed` = true when something was written that `onSaved` did not already announce. */
  onClose: (changed: boolean) => void;
  /** Called after each save, including the ones that keep the dialog open, with the saved row. */
  onSaved?: (entry: Entry) => void;
}) {
  const { t } = useI18n();
  const advanced = useAdvanced();
  const { fmt } = useMoney();
  const { ws, current } = useWorkspace();
  const { bump } = useAddEntry();
  const entryToast = useEntryToast();
  const toast = useToast();
  const shown = useOpenAfterMount();
  const baseCurrency = current?.base_currency ?? 'MXN';

  const [kind, setKind] = useState<EntryKind>(entry?.kind ?? initialKind);
  const [accounts, setAccounts] = useState<PfAccount[] | null>(null);
  const [labels, setLabels] = useState<Label[]>([]);
  const [pickerVersion, setPickerVersion] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [date, setDate] = useState(() => entry?.date ?? prefill?.date ?? todayLocalIso());
  // Stored unsigned; the API decides the sign from `kind`.
  const [amount, setAmount] = useState(() => unsigned(entry?.amount ?? prefill?.amount));
  const [labelId, setLabelId] = useState(entry?.label_id ?? prefill?.label_id ?? '');
  const [accountId, setAccountId] = useState(entry?.account_id ?? presetAccountId ?? prefill?.account_id ?? '');
  const [toAccountId, setToAccountId] = useState(entry?.to_account_id ?? prefill?.to_account_id ?? '');
  const [payee, setPayee] = useState(entry?.payee ?? prefill?.payee ?? '');
  const [note, setNote] = useState(entry?.note ?? prefill?.note ?? '');
  const [tags, setTags] = useState((entry?.tags ?? prefill?.tags ?? []).join(', '));
  // Sent verbatim: links the movement to a Mi dinero occurrence.
  const commitmentId = entry?.commitment_id ?? prefill?.commitment_id ?? null;
  // Receipt photo: the id the movement will carry, and what the last scan read.
  const [attachment, setAttachment] = useState<string | null>(entry?.attachment ?? null);
  const [scan, setScan] = useState<ReceiptScan | null>(null);
  const [splits, setSplits] = useState<SplitRow[]>(() =>
    (entry?.splits ?? prefill?.splits ?? []).map((s) => ({ key: splitSeq++, label_id: s.label_id, amount: unsigned(s.amount) })),
  );
  const [moreOpen, setMoreOpen] = useState(
    () =>
      (entry?.splits ?? prefill?.splits ?? []).length > 0 ||
      Boolean(entry?.payee || prefill?.payee || entry?.note || prefill?.note || (entry?.tags ?? prefill?.tags ?? []).length),
  );

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [splitErrors, setSplitErrors] = useState<Record<number, string>>({});
  const [splitProblem, setSplitProblem] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [focusKey, setFocusKey] = useState(0);
  const [savedCount, setSavedCount] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [payees, setPayees] = useState<string[] | null>(null);
  const payeesRequested = useRef(false);

  const isTransfer = kind === 'transfer';
  const editing = mode === 'edit' && entry !== null;

  /* ---- accounts + labels; the account default (accountId opt → last used → the single one → first) */
  useEffect(() => {
    if (!ws) return undefined;
    let alive = true;
    Promise.all([listPfAccounts(ws), listLabels(ws).catch(() => [] as Label[])])
      .then(([a, l]) => {
        if (!alive) return;
        const usable = a.filter((x) => !x.archived);
        setAccounts(usable);
        setLabels(l.filter((x) => !x.archived));
        setAccountId((prev) => {
          if (prev && usable.some((x) => x.id === prev)) return prev;
          const last = readLastAccount(ws);
          if (last && usable.some((x) => x.id === last)) return last;
          return usable[0]?.id ?? '';
        });
      })
      .catch((e: unknown) => {
        if (alive) {
          setAccounts([]);
          setLoadError(errorMessage(e, t));
        }
      });
    return () => {
      alive = false;
    };
  }, [ws, t]);

  // A transfer needs a destination that is not the source; keep the old "second account" default.
  useEffect(() => {
    if (!isTransfer || !accounts) return;
    setToAccountId((prev) => {
      // Only a default: a destination the person picked stays, even when it equals the source
      // (validation then says "Elige dos cuentas distintas" instead of silently changing it).
      if (prev && accounts.some((x) => x.id === prev)) return prev;
      return accounts.find((x) => x.id !== accountId)?.id ?? '';
    });
  }, [isTransfer, accounts, accountId]);

  /* ---- recent payees for the datalist, fetched once the details open */
  useEffect(() => {
    if (!moreOpen || !ws || payeesRequested.current) return undefined;
    payeesRequested.current = true;
    let alive = true;
    listEntries(ws, { limit: 500 })
      .then((page) => {
        if (!alive) return;
        const seen = new Set<string>();
        const out: string[] = [];
        for (const e of page.entries) {
          const p = e.payee?.trim();
          if (!p) continue;
          const k = p.toLowerCase();
          if (seen.has(k)) continue;
          seen.add(k);
          out.push(p);
          if (out.length >= PAYEE_LIMIT) break;
        }
        setPayees(out);
      })
      .catch(() => {
        if (alive) setPayees([]);
      });
    return () => {
      alive = false;
    };
  }, [moreOpen, ws]);

  const currency = accounts?.find((a) => a.id === accountId)?.currency ?? baseCurrency;
  const kindLabels = useMemo(
    () => labels.filter((l) => (l.kind ?? (l.account?.startsWith('Income:') ? 'income' : 'expense')) === kind),
    [labels, kind],
  );

  /* ---- validation (client courtesy; the API is the authority) */
  const validate = (): { ok: boolean; body?: EntryInput } => {
    const next: FieldErrors = {};
    const rowErrors: Record<number, string> = {};
    let problem: string | null = null;
    const amt = amount.trim();
    if (!isDecimalString(amt)) next.amount = t('v.amount');
    else if (decimalSign(amt) <= 0) next.amount = t('v.amount_positive');
    if (!ISO_DATE_RE.test(date)) next.date = t('v.date');
    if (!accountId) next.account = t('v.required');
    if (isTransfer) {
      if (!toAccountId) next.to = t('v.required');
      else if (toAccountId === accountId) next.to = t('add.same_account');
    }

    // Split rows: an empty row is dropped; a row with an amount and no category blocks the save
    // (never silently dropped); the parts must add up exactly to the amount.
    const rows = isTransfer ? [] : splits.filter((s) => s.label_id || s.amount.trim());
    for (const s of rows) {
      const a = s.amount.trim();
      if (!s.label_id) rowErrors[s.key] = t('add.split.missing_category');
      else if (!isDecimalString(a) || decimalSign(a) <= 0) rowErrors[s.key] = t('v.amount');
    }
    if (rows.length > 0 && Object.keys(rowErrors).length === 0 && !next.amount) {
      const sum = sumDecimals(rows.map((s) => s.amount));
      if (sum !== sumDecimals([amt])) {
        // parts − amount, shown as money: "−$150.00" = the parts fall short by 150.
        const diff = fmt({ amount: sumDecimals([sum, `-${amt}`]), currency }, { sign: 'always' });
        problem = `${t('add.split.mismatch')} ${t('add.split.difference', { diff })}`;
      }
    }

    setErrors(next);
    setSplitErrors(rowErrors);
    setSplitProblem(problem);
    if (Object.keys(next).length || Object.keys(rowErrors).length || problem) return { ok: false };

    const body: EntryInput = {
      kind,
      date,
      amount: { amount: amt, currency },
      account_id: accountId,
      to_account_id: isTransfer ? toAccountId : null,
      label_id: isTransfer ? null : labelId || null,
      payee: payee.trim() || null,
      note: note.trim() || null,
      tags: tags
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      splits: rows.length > 0 ? rows.map((s) => ({ label_id: s.label_id, amount: { amount: s.amount.trim(), currency } })) : null,
    };
    if (commitmentId) body.commitment_id = commitmentId;
    // Always sent: null clears a photo removed in edit mode (the API merges what is sent).
    body.attachment = attachment;
    return { ok: true, body };
  };

  /* ---- save (Enter) / save-and-add-another (Ctrl/Cmd+Enter) */
  const submit = async (again: boolean) => {
    if (busy || !ws) return;
    const { ok, body } = validate();
    if (!ok || !body) return;
    setBusy(true);
    setError(null);
    try {
      const row = editing && entry ? await updateEntry(ws, entry.id, body) : await createEntry(ws, body);
      writeLastAccount(ws, body.account_id);
      if (body.label_id) bumpCatUsage(ws, body.label_id);
      onSaved?.(row);
      if (editing) {
        // Edits have no undo: a plain confirmation once the dialog is gone.
        onClose(false);
        toast.success(t('txn.saved'));
        return;
      }
      // Toasts wait until the dialog closes; the in-dialog status line is what the person sees now.
      entryToast.saved(ws, row, bump);
      if (again) {
        setAmount('');
        setPayee('');
        setNote('');
        setAttachment(null);
        setScan(null);
        setSplits([]);
        setSplitErrors({});
        setSplitProblem(null);
        setErrors({});
        setStatus(entryToast.savedMessage(row));
        setSavedCount((n) => n + 1);
        setFocusKey((k) => k + 1);
      } else {
        onClose(false);
      }
    } catch (e) {
      const field = e instanceof ApiError ? e.field?.split('.').pop() : undefined;
      const msg = errorMessage(e, t);
      if (field === 'amount') setErrors((p) => ({ ...p, amount: msg }));
      else if (field === 'date') setErrors((p) => ({ ...p, date: msg }));
      else if (field === 'account_id') setErrors((p) => ({ ...p, account: msg }));
      else if (field === 'to_account_id') setErrors((p) => ({ ...p, to: msg }));
      else if (field === 'label_id') setErrors((p) => ({ ...p, label: msg }));
      else setError(msg);
    } finally {
      setBusy(false);
    }
  };

  /* ---- receipt photo: fill what is still empty; never overwrite what the person typed */
  const applyScan = (result: ReceiptScan) => {
    setScan(result);
    setAttachment(result.receipt.id);
    const s = result.suggestion;
    if (!s) return;
    if (s.amount && !amount.trim()) setAmount(s.amount.amount);
    if (s.label_id && !labelId) setLabelId(s.label_id);
    if (s.payee && !payee.trim()) setPayee(s.payee);
    if (s.date && !editing && date === todayLocalIso()) setDate(s.date);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !editing) {
      e.preventDefault();
      void submit(true);
    }
  };

  const onKindKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = KINDS.indexOf(kind);
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % KINDS.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + KINDS.length) % KINDS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = KINDS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    setKind(KINDS[next]);
    (e.currentTarget.parentElement?.children[next] as HTMLElement | undefined)?.focus();
  };

  const title = editing ? t('txn.edit') : mode === 'duplicate' ? t('add.mode.duplicate') : t('add.title');
  // Zero accounts is a *state*, not an error: the account form takes over the body.
  const noAccounts = accounts !== null && accounts.length === 0;
  const accountLabel = isTransfer ? t('add.account.from') : kind === 'income' ? t('add.account.income') : t('add.account');

  const noAccountsBody = (
    <div className={styles.dialogBody}>
      <p className={styles.hint}>{t('add.no_accounts')}</p>
      {ws && (
        <AccountForm
          ws={ws}
          inline
          onSaved={(a) => {
            setAccounts([a]);
            setAccountId(a.id);
            setPickerVersion((v) => v + 1);
            setLoadError(null);
          }}
        />
      )}
    </div>
  );

  const formBody = (
    // Ctrl/Cmd+Enter is a convenience on top of the form's own Enter (Dialog form mode).
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div className={styles.dialogBody} onKeyDown={onKeyDown}>
      {/* Tab semantics (not radiogroup): web-ui/tests/addentry.test.tsx pins [role=tab][aria-selected]. */}
      {!editing && (
        <div className={`ui-tabs ${styles.kinds}`} role="tablist" aria-label={t('add.kind.label')}>
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={k === kind}
              tabIndex={k === kind ? 0 : -1}
              onClick={() => setKind(k)}
              onKeyDown={onKindKey}
            >
              {t(`add.tab.${k}`)}
            </button>
          ))}
        </div>
      )}

      <p className={status ? styles.status : 'sr-only'} role="status" aria-live="polite">
        {status ?? ''}
      </p>

      {ws && (kind === 'expense' || attachment) && (
        <ReceiptScanner
          ws={ws}
          attachment={attachment}
          scan={scan}
          onScanned={applyScan}
          onRemove={() => {
            setAttachment(null);
            setScan(null);
          }}
          disabled={busy}
        />
      )}

      {/* `focusKey` starts defined, so MoneyInput focuses itself on mount (amount-first) and again after save-and-add-another. */}
      <Field label={t('add.amount')} required error={errors.amount}>
        <MoneyInput value={amount} onChange={setAmount} currency={currency} focusKey={focusKey} name="amount" />
      </Field>

      {!isTransfer && ws && (
        <>
          <CategoryChips ws={ws} kind={kind} labels={labels} value={labelId} onPick={(id) => setLabelId(id)} version={savedCount} />
          <Field
            label={t('add.category')}
            error={errors.label}
            hint={kindLabels.length === 0 ? t('add.no_categories') : kind === 'income' && !labelId ? t('add.income.no_category') : undefined}
          >
            <CategoryPicker ws={ws} kind={kind} value={labelId} onChange={(id) => setLabelId(id)} allowNew version={pickerVersion} />
          </Field>
        </>
      )}

      <Field label={accountLabel} required error={errors.account}>
        <AccountPicker ws={ws} value={accountId} onChange={(id) => setAccountId(id)} version={pickerVersion} />
      </Field>

      {isTransfer && (
        <Field label={t('add.account.to')} required error={errors.to}>
          <AccountPicker ws={ws} value={toAccountId} onChange={(id) => setToAccountId(id)} version={pickerVersion} />
        </Field>
      )}

      <Field label={t('add.date')} required error={errors.date}>
        <DateField value={date} onChange={setDate} todayYesterdayChips />
      </Field>

      {commitmentId && !editing && <p className={styles.hint}>{t('add.commitment.hint')}</p>}

      <details className={styles.more} open={moreOpen} onToggle={(e) => setMoreOpen(e.currentTarget.open)}>
        <summary>{t('add.more')}</summary>
        <Field label={t('add.payee')}>
          <Input value={payee} onChange={(e) => setPayee(e.target.value)} list="add-entry-payees" autoComplete="off" />
        </Field>
        <datalist id="add-entry-payees">
          {(payees ?? []).map((p) => (
            <option key={p} value={p} />
          ))}
        </datalist>
        <Field label={t('add.note')}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
        </Field>
        <Field label={t('add.tags')} hint={t('add.tags.hint')}>
          <Input value={tags} onChange={(e) => setTags(e.target.value)} />
        </Field>

        {!isTransfer && ws && (
          <div role="group" aria-label={t('add.split')}>
            <span className="ui-field-label small muted">{t('add.split')}</span>
            {splits.map((s) => (
              <div className={styles.splitRow} key={s.key}>
                <Field label={t('add.category')} error={splitErrors[s.key]}>
                  <CategoryPicker
                    ws={ws}
                    kind={kind}
                    value={s.label_id}
                    onChange={(id) => setSplits((prev) => prev.map((x) => (x.key === s.key ? { ...x, label_id: id } : x)))}
                    version={pickerVersion}
                  />
                </Field>
                <Field label={t('add.amount')}>
                  <MoneyInput
                    value={s.amount}
                    onChange={(val) => setSplits((prev) => prev.map((x) => (x.key === s.key ? { ...x, amount: val } : x)))}
                    currency={currency}
                  />
                </Field>
                <Button variant="ghost" onClick={() => setSplits((prev) => prev.filter((x) => x.key !== s.key))}>
                  {t('add.split.remove')}
                </Button>
              </div>
            ))}
            <div className={styles.splitActions}>
              <Button variant="secondary" onClick={() => setSplits((prev) => [...prev, { key: splitSeq++, label_id: '', amount: '' }])}>
                {t('add.split.add')}
              </Button>
              {splits.length > 0 && (
                <span className="small muted">
                  {t('add.split.sum')}: <Money amount={{ amount: sumDecimals(splits.map((s) => s.amount)), currency }} />
                </span>
              )}
            </div>
            {splitProblem && (
              <p className="ui-field-error" role="alert">
                {splitProblem}
              </p>
            )}
          </div>
        )}
      </details>

      <div className={styles.dialogActions}>
        {!editing && (
          <Button variant="secondary" onClick={() => void submit(true)} disabled={busy}>
            {t('add.save_another')}
          </Button>
        )}
        {editing && (
          <Button variant="ghost" onClick={() => setConfirmDelete(true)} disabled={busy}>
            {t('add.delete')}
          </Button>
        )}
      </div>
      {/* Keyboard tips are for people who already know the app (advanced mode). */}
      {advanced && <p className={styles.tip}>{t('add.tip.shortcut')}</p>}
    </div>
  );

  return (
    <>
      <Dialog
        open={shown}
        title={title}
        onClose={() => onClose(false)}
        size="md"
        form={noAccounts ? undefined : { onSubmit: () => void submit(false), busy: busy || accounts === null, submitLabel: t('common.save') }}
        error={error ?? loadError}
      >
        {noAccounts ? noAccountsBody : formBody}
      </Dialog>
      {confirmDelete && entry && ws && (
        <DeleteEntryDialog
          ws={ws}
          entry={entry}
          bump={bump}
          onDone={() => {
            setConfirmDelete(false);
            onClose(false);
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  );
}

/** The header button. Kept here so the primary action and its dialog stay together. */
export function AddEntryButton() {
  const { t } = useI18n();
  const { open } = useAddEntry();
  const onClick = useCallback(() => open('expense'), [open]);
  return (
    <Button variant="primary" onClick={onClick} className="topbar-add">
      + {t('add.button')}
    </Button>
  );
}
