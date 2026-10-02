'use client';

/**
 * `CommitmentForm` — the one form for a fixed payment.
 *
 * Two shells over one body:
 *   - `inline` (the onboarding wizard, where its submit is the step's only primary): a bare
 *     `<form>` with its own 'Guardar pago fijo' submit, no dialog, no toast, optional `onCancel`;
 *   - `CommitmentDialog`: the same body inside `ui/Dialog` in form mode (Enter submits, Esc
 *     closes, focus returns to the opener).
 *
 * Personal fields only: the account is picked by name (`account_id`, never a ledger string),
 * the category through `CategoryPicker`, the day of the month through a select where 31
 * means 'último día' (the server clamps), weekdays travel in Python order (Monday = 0). Create
 * sends `merchant_patterns: []` and `status: 'active'`; edit diffs against the row and sends
 * only what changed (`patchCommitment` = PATCH-merge). A duplicate-name 409 is shown inline
 * with a link to the existing row and a 'Guardar de todas formas' (`force: true`).
 *
 * `initial.kind` accepts any `CommitmentKind`; the six chips cover subscription / utility /
 * rent / loan_payment ('Préstamo o tarjeta' — Home's 'Tarjeta' chip) / insurance / bill; a
 * kind outside those renders as 'Otro' and is sent unchanged.
 *
 * On screen only what a person must answer — what it is, name, amount, how often
 * and when the next one is. The day of the month follows the next date; the paying account is
 * auto-picked; a new payment's category follows its kind (seeded names, until the person picks
 * one); account, category, exact day, auto-pay, essential and notes sit behind "Más opciones".
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  AccountPicker,
  Button,
  CategoryPicker,
  DateField,
  Dialog,
  Field,
  Input,
  MoneyInput,
  MoreOptions,
  Select,
  Textarea,
} from '@/components/ui';
import { ApiError, createCommitment, errorMessage, listLabels, patchCommitment } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n, useMoney, type MsgKey } from '@/lib/i18n';
import { CADENCES, type Cadence, type Commitment, type CommitmentInput, type CommitmentKind, type CommitmentPatch, type Essential } from '@/lib/types-organizer';
import { isMonthCadence, isWeekCadence, KIND_OPTIONS, useOpenAfterMount, weekdayName } from './shared';
import styles from './money.module.css';

/* ------------------------------------------------------------ state ------ */

interface FormState {
  name: string;
  kind: CommitmentKind;
  amount: string;
  currency: string;
  amountVariable: boolean;
  accountId: string;
  labelId: string;
  cadence: Cadence;
  intervalDays: string;
  /** 1..31 as a string; '' when the cadence has no day. */
  anchorDay: string;
  /** Python weekday 0..6 as a string. */
  weekday: string;
  nextDue: string;
  autoPay: boolean;
  essential: boolean;
  notes: string;
}

const AMOUNT_RE = /^\d{1,15}(\.\d{1,2})?$/;

function dayOf(iso: string): string {
  const m = /^\d{4}-\d{2}-(\d{2})$/.exec(iso);
  return m ? String(Number(m[1])) : '';
}

function fromCommitment(c: Partial<Commitment> | Partial<CommitmentInput> | undefined, base: string): FormState {
  const kind = (c?.kind as CommitmentKind | undefined) ?? 'subscription';
  const nextDue = c?.next_due ?? '';
  return {
    name: c?.name ?? '',
    kind,
    amount: c?.amount?.amount ?? '',
    currency: c?.amount?.currency ?? base,
    amountVariable: c?.amount_variable ?? false,
    accountId: c?.account_id ?? '',
    labelId: c?.label_id ?? '',
    cadence: (c?.cadence as Cadence | undefined) ?? 'monthly',
    intervalDays: c?.interval_days != null ? String(c.interval_days) : '',
    anchorDay: c?.anchor_day != null ? String(c.anchor_day) : dayOf(nextDue),
    weekday: c?.weekday != null ? String(c.weekday) : '',
    nextDue,
    autoPay: c?.auto_pay ?? false,
    essential: c?.essential ? c.essential === 'needs' || c.essential === 'debt' : kind === 'rent' || kind === 'utility' || kind === 'loan_payment' || kind === 'insurance',
    notes: c?.notes ?? '',
  };
}

function toInput(s: FormState): CommitmentInput {
  const essential: Essential = s.kind === 'loan_payment' ? 'debt' : s.essential ? 'needs' : 'wants';
  const month = isMonthCadence(s.cadence);
  const week = isWeekCadence(s.cadence);
  return {
    kind: s.kind,
    name: s.name.trim(),
    merchant_patterns: [],
    amount: { amount: s.amount, currency: s.currency },
    amount_variable: s.amountVariable,
    cadence: s.cadence,
    interval_days: s.cadence === 'custom' ? Number(s.intervalDays) : null,
    anchor_day: month ? Number(s.anchorDay || dayOf(s.nextDue) || '1') : null,
    weekday: week && s.weekday !== '' ? Number(s.weekday) : null,
    next_due: s.nextDue,
    account_id: s.accountId || null,
    label_id: s.labelId || null,
    essential,
    status: 'active',
    auto_pay: s.autoPay,
    notes: s.notes.trim() ? s.notes.trim() : null,
  };
}

/** Only the keys whose value differs from the stored row (PUT = PATCH-merge). */
function diffPatch(input: CommitmentInput, c: Commitment): CommitmentPatch {
  const out: CommitmentPatch = {};
  const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  if (input.name !== c.name) out.name = input.name;
  if (input.kind !== c.kind) out.kind = input.kind;
  if (input.amount.amount !== c.amount.amount || input.amount.currency !== c.amount.currency) out.amount = input.amount;
  if (Boolean(input.amount_variable) !== Boolean(c.amount_variable)) out.amount_variable = input.amount_variable;
  if (input.cadence !== c.cadence) out.cadence = input.cadence;
  if (!same(input.interval_days, c.interval_days)) out.interval_days = input.interval_days;
  if (!same(input.anchor_day, c.anchor_day)) out.anchor_day = input.anchor_day;
  if (!same(input.weekday, c.weekday)) out.weekday = input.weekday;
  if (input.next_due !== c.next_due) out.next_due = input.next_due;
  if (!same(input.account_id, c.account_id)) out.account_id = input.account_id;
  if (!same(input.label_id, c.label_id)) out.label_id = input.label_id;
  if (input.essential !== c.essential) out.essential = input.essential;
  if (Boolean(input.auto_pay) !== Boolean(c.auto_pay)) out.auto_pay = input.auto_pay;
  if (!same(input.notes, c.notes)) out.notes = input.notes;
  return out;
}

interface Duplicate {
  existingId: string;
  name: string;
}

function duplicateOf(e: unknown, name: string): Duplicate | null {
  if (!(e instanceof ApiError) || e.status !== 409) return null;
  const d = e.detail as { code?: string; existing_id?: string; existing_name?: string } | null;
  if (!d || typeof d !== 'object' || d.code !== 'duplicate') return null;
  return { existingId: String(d.existing_id ?? ''), name: d.existing_name ?? name };
}

/* ------------------------------------------------------------- hook ------ */

export interface CommitmentFormProps {
  ws: string;
  /** Bare `<form>` with its own submit (wizard); else use `CommitmentDialog`. */
  inline?: boolean;
  initial?: Partial<CommitmentInput>;
  /** Edit mode: diff against this row and send only the changed keys. */
  commitment?: Commitment | null;
  onSaved: (commitment: Commitment) => void;
  onCancel?: () => void;
  /** 'editar el existente' on a duplicate 409 (the list opens the drawer). */
  onOpenExisting?: (id: string) => void;
}

function useCommitmentForm({ ws, initial, commitment, onSaved }: CommitmentFormProps) {
  const { t } = useI18n();
  const { base } = useMoney();
  const [s, setS] = useState<FormState>(() => fromCommitment(commitment ?? initial, base));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<'name' | 'amount' | 'nextDue' | 'intervalDays', string>>>({});
  const [dup, setDup] = useState<Duplicate | null>(null);

  // 'Próximo pago' defaults to today — read the clock after mount, never at prerender.
  useEffect(() => {
    setS((prev) => (prev.nextDue ? prev : { ...prev, nextDue: todayLocalIso(), anchorDay: prev.anchorDay || dayOf(todayLocalIso()) }));
  }, []);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setS((prev) => ({ ...prev, [k]: v }));

  const validate = (): boolean => {
    const errs: typeof fieldErrors = {};
    if (!s.name.trim()) errs.name = t('v.name_short');
    if (!AMOUNT_RE.test(s.amount)) errs.amount = t('v.amount');
    else if (/^0+(\.0+)?$/.test(s.amount) && !s.amountVariable) errs.amount = t('v.amount_positive');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s.nextDue)) errs.nextDue = t('v.date');
    if (s.cadence === 'custom' && !(Number(s.intervalDays) >= 1)) errs.intervalDays = t('v.required');
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const submit = async (force = false) => {
    if (busy) return;
    if (!validate()) return;
    setBusy(true);
    setError(null);
    setDup(null);
    const input = toInput(s);
    try {
      let saved: Commitment;
      if (commitment) {
        const patch = diffPatch(input, commitment);
        saved = Object.keys(patch).length === 0 ? commitment : await patchCommitment(ws, commitment.id, { ...patch, ...(force ? { force: true } : {}) });
      } else {
        saved = await createCommitment(ws, { ...input, ...(force ? { force: true } : {}) });
      }
      onSaved(saved);
    } catch (e) {
      const d = duplicateOf(e, input.name);
      if (d) setDup(d);
      else setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return { s, set, busy, error, fieldErrors, dup, submit };
}

/* ------------------------------------------------------------- fields ---- */

/** Seeded category names (aurum/pf/labels.py) a new payment of each kind files under. */
const KIND_CATEGORY: Partial<Record<CommitmentKind, string>> = {
  rent: 'Renta/Hipoteca',
  utility: 'Servicios (luz/agua/gas)',
  subscription: 'Software/Suscripciones',
  insurance: 'Seguros',
};

/** Python weekday (Monday = 0) of a local ISO date, or '' when it is not one. */
function weekdayOf(iso: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return String((new Date(y, m - 1, d).getDay() + 6) % 7);
}

type Form = ReturnType<typeof useCommitmentForm>;

function Fields({
  ws,
  form,
  editing,
  onOpenExisting,
}: {
  ws: string;
  form: Form;
  editing: boolean;
  onOpenExisting?: (id: string) => void;
}) {
  const { t, lang } = useI18n();
  const { s, set, fieldErrors, dup, error, submit, busy } = form;
  const kindSelected = KIND_OPTIONS.some((k) => k.kind === s.kind) ? s.kind : 'bill';
  const month = isMonthCadence(s.cadence);
  const week = isWeekCadence(s.cadence);
  const days = useMemo(() => Array.from({ length: 30 }, (_, i) => i + 1), []);
  const [labelTouched, setLabelTouched] = useState(editing || Boolean(s.labelId));
  const [categoryByName, setCategoryByName] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    if (editing || !ws) return undefined;
    let alive = true;
    listLabels(ws, { kind: 'expense' })
      .then((rows) => {
        if (alive) setCategoryByName(new Map((Array.isArray(rows) ? rows : []).map((l) => [l.name, l.id])));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [ws, editing]);

  // A new payment's category follows its kind until the person picks one by hand.
  useEffect(() => {
    if (labelTouched) return;
    const name = KIND_CATEGORY[s.kind];
    set('labelId', (name && categoryByName.get(name)) || '');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `set` is a fresh closure per render
  }, [s.kind, categoryByName, labelTouched]);

  return (
    <div className={styles.form}>
      <Field label={t('money.f.what')} asGroup>
        <div className={['ui-chips', styles.segment].join(' ')}>
          {KIND_OPTIONS.map((k) => (
            <button
              key={k.kind}
              type="button"
              className="ui-chip"
              aria-pressed={kindSelected === k.kind}
              onClick={() => set('kind', k.kind === 'bill' && !KIND_OPTIONS.some((o) => o.kind === s.kind) ? s.kind : k.kind)}
            >
              {t(k.key)}
            </button>
          ))}
        </div>
      </Field>

      <Field label={t('money.f.name')} required error={fieldErrors.name}>
        <Input value={s.name} onChange={(e) => set('name', e.target.value)} autoComplete="off" data-autofocus />
      </Field>

      <Field label={t('money.f.amount')} required error={fieldErrors.amount}>
        <MoneyInput value={s.amount} onChange={(v) => set('amount', v)} currency={s.currency} />
      </Field>

      <label className={styles.check}>
        <input type="checkbox" checked={s.amountVariable} onChange={(e) => set('amountVariable', e.target.checked)} />
        <span className={styles.checkText}>
          {t('money.f.variable')}
          <span className={styles.checkHint}>{t('money.f.variable.hint')}</span>
        </span>
      </label>

      <div className={styles.twoCols}>
        <Field label={t('money.f.cadence')}>
          <Select
            value={s.cadence}
            onChange={(e) => {
              const c = e.target.value as Cadence;
              set('cadence', c);
              if (isMonthCadence(c) && !s.anchorDay) set('anchorDay', dayOf(s.nextDue) || '1');
              if (isWeekCadence(c) && s.weekday === '') set('weekday', weekdayOf(s.nextDue));
            }}
          >
            {CADENCES.map((c) => (
              <option key={c} value={c}>
                {t(`money.cadence.${c}` as MsgKey)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('money.f.next')} required error={fieldErrors.nextDue}>
          <DateField
            value={s.nextDue}
            onChange={(iso) => {
              set('nextDue', iso);
              if (month) set('anchorDay', dayOf(iso) || s.anchorDay);
              if (week) set('weekday', weekdayOf(iso) || s.weekday);
            }}
            todayYesterdayChips={false}
          />
        </Field>
      </div>

      {s.cadence === 'custom' && (
        <Field label={t('money.f.interval')} required error={fieldErrors.intervalDays}>
          <Input type="number" inputMode="numeric" min={1} value={s.intervalDays} onChange={(e) => set('intervalDays', e.target.value)} />
        </Field>
      )}

      <MoreOptions>
        <div className={styles.twoCols}>
          <Field label={t('money.f.account')}>
            <AccountPicker
              ws={ws}
              value={s.accountId}
              autoPick={!editing}
              onChange={(id, account) => {
                set('accountId', id);
                if (account?.currency) set('currency', account.currency.toUpperCase());
              }}
            />
          </Field>
          <Field label={t('money.f.category')}>
            <CategoryPicker
              ws={ws}
              kind="expense"
              value={s.labelId}
              onChange={(id) => {
                setLabelTouched(true);
                set('labelId', id);
              }}
              allowNew
            />
          </Field>
        </div>

        {month && (
          <Field label={t('money.f.day')}>
            <Select value={s.anchorDay || '1'} onChange={(e) => set('anchorDay', e.target.value)}>
              {days.map((d) => (
                <option key={d} value={String(d)}>
                  {t('money.f.day_n', { n: d })}
                </option>
              ))}
              <option value="31">{t('money.f.last_day')}</option>
            </Select>
          </Field>
        )}
        {week && (
          <Field label={t('money.f.weekday')}>
            <Select value={s.weekday || '0'} onChange={(e) => set('weekday', e.target.value)}>
              {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                <option key={d} value={String(d)}>
                  {weekdayName(d, lang)}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <label className={styles.check}>
          <input type="checkbox" checked={s.autoPay} onChange={(e) => set('autoPay', e.target.checked)} />
          <span className={styles.checkText}>
            {t('money.f.auto_pay')}
            <span className={styles.checkHint}>{t('money.f.auto_pay.hint')}</span>
          </span>
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={s.kind === 'loan_payment' ? true : s.essential}
            disabled={s.kind === 'loan_payment'}
            onChange={(e) => set('essential', e.target.checked)}
          />
          <span className={styles.checkText}>
            {t('money.f.essential')}
            <span className={styles.checkHint}>{t('money.f.essential.hint')}</span>
          </span>
        </label>

        <Field label={t('money.f.notes')}>
          <Textarea rows={2} value={s.notes} onChange={(e) => set('notes', e.target.value)} />
        </Field>
      </MoreOptions>

      {dup && (
        <p className={styles.dup} role="alert">
          <span>{t('money.fixed.duplicate', { name: dup.name })}</span>
          {onOpenExisting && dup.existingId && (
            <>
              <span aria-hidden="true">—</span>
              <button type="button" className={styles.linkBtn} onClick={() => onOpenExisting(dup.existingId)}>
                {t('money.fixed.duplicate.open')}
              </button>
            </>
          )}
          <Button variant="secondary" onClick={() => void submit(true)} disabled={busy}>
            {t('money.fixed.duplicate.force')}
          </Button>
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- shells ---- */

/** `inline` → bare form; otherwise the same body inside a Dialog that is always open. */
export function CommitmentForm(props: CommitmentFormProps) {
  const { t } = useI18n();
  const form = useCommitmentForm(props);
  const mounted = useOpenAfterMount();
  const [closed, setClosed] = useState(false);

  if (props.inline) {
    const onSubmit = (e: FormEvent) => {
      e.preventDefault();
      void form.submit();
    };
    return (
      <form onSubmit={onSubmit} aria-busy={form.busy || undefined} className={styles.form}>
        <Fields ws={props.ws} form={form} editing={Boolean(props.commitment)} onOpenExisting={props.onOpenExisting} />
        <div className={styles.formFoot}>
          {props.onCancel && (
            <Button variant="ghost" onClick={props.onCancel} disabled={form.busy}>
              {t('common.cancel')}
            </Button>
          )}
          <span className={styles.grow} />
          <Button type="submit" variant="primary" loading={form.busy}>
            {t('money.f.save')}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <Dialog
      open={mounted && !closed}
      onClose={() => {
        setClosed(true);
        props.onCancel?.();
      }}
      title={props.commitment ? t('money.fixed.edit_title') : t('money.fixed.new_title')}
      size="lg"
      form={{ onSubmit: () => void form.submit(), busy: form.busy, submitLabel: t('money.f.save') }}
    >
      <Fields ws={props.ws} form={form} editing={Boolean(props.commitment)} onOpenExisting={props.onOpenExisting} />
    </Dialog>
  );
}

export interface CommitmentDialogProps {
  ws: string;
  open: boolean;
  onClose: () => void;
  commitment?: Commitment | null;
  initial?: Partial<CommitmentInput>;
  onSaved: (commitment: Commitment) => void;
  onOpenExisting?: (id: string) => void;
}

/**
 * The list's dialog: mounts the form (and its state) only while open, so a second 'Nuevo'
 * starts clean and the native dialog returns focus to the opener on close.
 */
export function CommitmentDialog({ ws, open, onClose, commitment, initial, onSaved, onOpenExisting }: CommitmentDialogProps) {
  if (!open) return null;
  return <CommitmentForm ws={ws} commitment={commitment} initial={initial} onSaved={onSaved} onCancel={onClose} onOpenExisting={onOpenExisting} />;
}
