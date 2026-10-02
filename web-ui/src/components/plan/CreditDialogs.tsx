'use client';

/**
 * Credit dialogs of `/plan/?tab=credit`, on `ui/Dialog`.
 *
 * - `CardDialog` / `LoanDialog` create a **pf account** (`POST /pf/{ws}/accounts` with
 *   `type: credit_card | loan`) — the server's `create_account` writes the matching
 *   `pf_credit_cards` / `pf_loans` row itself, so `POST /credit/cards|loans` is no longer called
 *   by the UI. The opening balance is what is owed, typed positive (the server negates).
 *   APR is collected as a percent (`apr_percent`, "14") and never divided.
 * - Edit terms (`mode: 'edit'`) picks the card/loan through `AccountPicker` (or arrives with the
 *   row's `accountId` preselected) and sends `PUT /pf/{ws}/accounts/{id}` with **only the terms
 *   the user changed** (`cut_day`, `due_day`, `credit_limit`, `apr_percent` / `apr_percent`,
 *   `loan_months`). The fields are seeded from the account itself — `AccountPicker` reports
 *   user changes only, so a preselected id is resolved through `listPfAccounts` — and an
 *   untouched save sends nothing (the defaults used to overwrite the card's real cut/due
 *   days).
 * - `MsiDialog` keeps `POST /credit/cards/{card_id}/msi` (the card row id, `card-…`, not the
 *   account id). `ScoreDialog` keeps `POST /credit/scores`.
 * No "(verify)" markers and no "no endpoint" notices reach the screen.
 */
import { useEffect, useState } from 'react';
import { AccountPicker, DateField, Dialog, Field, Input, MoneyInput, useToast } from '@/components/ui';
import { createMsi, createPfAccount, createScore, errorMessage, listPfAccounts, updatePfAccount } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import * as v from '@/lib/validate';
import { useWorkspace } from '@/lib/workspace';
import type { PfAccount, PfAccountInput } from '@/lib/types-personal';

type Close = (saved: boolean) => void;

function useForm(onClose: Close, savedMsg: string) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onClose(true);
      toast.success(savedMsg);
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, touched, setTouched, run };
}

const intOrNull = (s: string): number | null => (s.trim() ? Number(s.trim()) : null);

/**
 * Edit mode: the account whose terms are being edited. `AccountPicker.onChange` hands it over on
 * a user change; a preselected `accountId` (the row's "Editar términos") is resolved here from
 * `listPfAccounts` (archived included — the row may be an archived card). `resolving` keeps the
 * submit disabled until the terms are seeded, so the defaults can never be written back.
 */
function useEditAccount(ws: string, editing: boolean, accountId: string | null | undefined) {
  const { t } = useI18n();
  const [picked, setPicked] = useState(accountId ?? '');
  const [account, setAccount] = useState<PfAccount | null>(null);
  const [resolving, setResolving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const accountKey = account?.id ?? null;

  useEffect(() => {
    if (!editing || !picked || accountKey === picked) return undefined;
    let alive = true;
    setResolving(true);
    setLoadError(null);
    listPfAccounts(ws, { includeArchived: true })
      .then((rows) => {
        if (!alive) return;
        const found = rows.find((a) => a.id === picked) ?? null;
        setAccount(found);
        if (!found) setLoadError(t('err.not_found'));
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(errorMessage(e, t));
      })
      .finally(() => {
        if (alive) setResolving(false);
      });
    return () => {
      alive = false;
    };
  }, [ws, editing, picked, accountKey, t]);

  const pick = (id: string, a: PfAccount | null) => {
    setPicked(id);
    setAccount(a);
    setLoadError(null);
  };
  /** The picked id has its terms on screen (nothing to submit before that). */
  const ready = !editing || (Boolean(picked) && accountKey === picked);
  return { picked, account, resolving, loadError, pick, ready };
}

/** The card terms as the inputs hold them (strings; '' when the account has none). */
export function cardTerms(a: PfAccount | null): { cutDay: string; dueDay: string; limit: string; apr: string } {
  return {
    cutDay: a?.cut_day ? String(a.cut_day) : '',
    dueDay: a?.due_day ? String(a.due_day) : '',
    limit: a?.credit_limit?.amount ?? '',
    apr: a?.apr_percent ?? '',
  };
}

/** The loan terms as the inputs hold them. */
export function loanTerms(a: PfAccount | null): { apr: string; months: string } {
  return {
    apr: a?.apr_percent ?? '',
    months: a?.loan_months ? String(a.loan_months) : '',
  };
}

/* ------------------------------------------------------------------ cards */

export interface CardDialogProps {
  ws: string;
  mode?: 'create' | 'edit';
  /** Edit mode: the pf account to preselect (matched from the card row's `account`). */
  accountId?: string | null;
  onClose: Close;
}

export function CardDialog({ ws, mode = 'create', accountId, onClose }: CardDialogProps) {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const editing = mode === 'edit';
  const { busy, error, touched, setTouched, run } = useForm(onClose, editing ? t('card.terms_saved') : t('card.saved'));
  const base = (current?.base_currency ?? 'MXN').toUpperCase();

  const { picked, account, resolving, loadError, pick, ready } = useEditAccount(ws, editing, accountId);
  const [name, setName] = useState('');
  const [institution, setInstitution] = useState('');
  const [currency, setCurrency] = useState(base);
  const [owed, setOwed] = useState('');
  const [limit, setLimit] = useState('');
  const [cutDay, setCutDay] = useState(editing ? '' : '1');
  const [dueDay, setDueDay] = useState(editing ? '' : '20');
  const [apr, setApr] = useState('');

  // Editing: the account's current terms are what the fields start from (and the baseline the
  // submit diffs against).
  const seed = cardTerms(account);
  useEffect(() => {
    if (!account) return;
    const s = cardTerms(account);
    setCutDay(s.cutDay);
    setDueDay(s.dueDay);
    setLimit(s.limit);
    setApr(s.apr);
  }, [account]);

  const errors = {
    picked: editing ? v.required(picked) : null,
    name: editing ? null : v.required(name),
    currency: editing ? null : v.currency(currency),
    owed: editing || !owed.trim() ? null : v.decimal(owed, { positive: true }),
    limit: limit.trim() ? v.decimal(limit, { positive: true }) : null,
    cut_day: editing && !cutDay.trim() ? null : v.integer(cutDay, 1, 31),
    due_day: editing && !dueDay.trim() ? null : v.integer(dueDay, 1, 31),
    apr: apr.trim() ? v.rate(apr) : null,
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);
  const cur = editing ? (account?.currency ?? base).toUpperCase() : currency.trim().toUpperCase() || base;

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    if (editing) {
      if (!ready) return; // the submit is disabled while the terms load; belt and braces
      // Only what changed travels: an untouched save is a no-op (never the defaults).
      const body: Partial<PfAccountInput> = {};
      if (cutDay.trim() !== seed.cutDay) body.cut_day = intOrNull(cutDay);
      if (dueDay.trim() !== seed.dueDay) body.due_day = intOrNull(dueDay);
      if (apr.trim() !== seed.apr) body.apr_percent = apr.trim() || null;
      if (limit.trim() !== seed.limit) body.credit_limit = limit.trim() ? { amount: limit.trim(), currency: cur } : null;
      if (Object.keys(body).length === 0) {
        onClose(false);
        return;
      }
      void run(() => updatePfAccount(ws, picked, body));
      return;
    }
    const body: PfAccountInput = {
      type: 'credit_card',
      name: name.trim(),
      institution: institution.trim() || null,
      currency: cur,
      opening_balance: { amount: owed.trim() || '0', currency: cur },
      credit_limit: limit.trim() ? { amount: limit.trim(), currency: cur } : null,
      cut_day: intOrNull(cutDay),
      due_day: intOrNull(dueDay),
      apr_percent: apr.trim() || null,
    };
    void run(() => createPfAccount(ws, body));
  };

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={editing ? t('card.edit_terms') : t('card.new')}
      form={{ onSubmit: submit, busy: busy || resolving, submitLabel: t('common.save') }}
      error={error ?? loadError}
    >
      {editing ? (
        <Field label={t('card.pick')} required error={show('picked')}>
          <AccountPicker ws={ws} value={picked} filterTypes={['credit_card']} onChange={pick} />
        </Field>
      ) : (
        <>
          <Field label={t('card.name')} required error={show('name')}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-autofocus />
          </Field>
          <Field label={t('card.institution')} hint={t('form.optional')}>
            <Input value={institution} onChange={(e) => setInstitution(e.target.value)} maxLength={80} />
          </Field>
          <Field label={t('common.currency')} required error={show('currency')}>
            <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
          </Field>
          <Field label={t('card.owed')} hint={t('form.optional')} error={show('owed')}>
            <MoneyInput value={owed} onChange={setOwed} currency={cur} />
          </Field>
        </>
      )}
      <Field label={t('card.limit')} hint={t('form.optional')} error={show('limit')}>
        <MoneyInput value={limit} onChange={setLimit} currency={cur} />
      </Field>
      <Field label={t('card.cut_day')} required={!editing} error={show('cut_day')}>
        <Input inputMode="numeric" value={cutDay} onChange={(e) => setCutDay(e.target.value.replace(/\D/g, ''))} />
      </Field>
      <Field label={t('card.due_day')} required={!editing} error={show('due_day')}>
        <Input inputMode="numeric" value={dueDay} onChange={(e) => setDueDay(e.target.value.replace(/\D/g, ''))} />
      </Field>
      <Field label={t('card.apr_percent')} hint={t('form.optional')} error={show('apr')}>
        <Input inputMode="decimal" value={apr} onChange={(e) => setApr(e.target.value.replace(/[^\d.]/g, ''))} placeholder="36" />
      </Field>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ loans */

export interface LoanDialogProps {
  ws: string;
  mode?: 'create' | 'edit';
  accountId?: string | null;
  onClose: Close;
}

export function LoanDialog({ ws, mode = 'create', accountId, onClose }: LoanDialogProps) {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const editing = mode === 'edit';
  const { busy, error, touched, setTouched, run } = useForm(onClose, editing ? t('card.terms_saved') : t('loan.saved'));
  const base = (current?.base_currency ?? 'MXN').toUpperCase();

  const { picked, account, resolving, loadError, pick, ready } = useEditAccount(ws, editing, accountId);
  const [name, setName] = useState('');
  const [institution, setInstitution] = useState('');
  const [currency, setCurrency] = useState(base);
  const [owed, setOwed] = useState('');
  const [principal, setPrincipal] = useState('');
  const [apr, setApr] = useState('');
  const [months, setMonths] = useState('');
  const [start, setStart] = useState('');

  useEffect(() => {
    if (editing) return;
    setStart((s) => s || todayLocalIso());
  }, [editing]);

  const seed = loanTerms(account);
  useEffect(() => {
    if (!account) return;
    const s = loanTerms(account);
    setApr(s.apr);
    setMonths(s.months);
  }, [account]);

  const errors = {
    picked: editing ? v.required(picked) : null,
    name: editing ? null : v.required(name),
    currency: editing ? null : v.currency(currency),
    owed: editing ? null : v.decimal(owed, { positive: true }),
    principal: !editing && principal.trim() ? v.decimal(principal, { positive: true }) : null,
    apr: apr.trim() ? v.rate(apr) : null,
    months: months.trim() ? v.integer(months, 1, 600) : editing ? null : ('valid.required' as const),
    start: editing || !start.trim() ? null : v.isoDate(start),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);
  const cur = editing ? (account?.currency ?? base).toUpperCase() : currency.trim().toUpperCase() || base;

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    if (editing) {
      if (!ready) return;
      const body: Partial<PfAccountInput> = {};
      if (apr.trim() !== seed.apr) body.apr_percent = apr.trim() || null;
      if (months.trim() !== seed.months) body.loan_months = intOrNull(months);
      if (Object.keys(body).length === 0) {
        onClose(false);
        return;
      }
      void run(() => updatePfAccount(ws, picked, body));
      return;
    }
    const body: PfAccountInput = {
      type: 'loan',
      name: name.trim(),
      institution: institution.trim() || null,
      currency: cur,
      opening_balance: { amount: owed.trim(), currency: cur },
      opening_date: start.trim() || null,
      apr_percent: apr.trim() || null,
      loan_months: intOrNull(months),
      loan_principal: principal.trim() ? { amount: principal.trim(), currency: cur } : null,
    };
    void run(() => createPfAccount(ws, body));
  };

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={editing ? t('loan.edit_terms') : t('loan.new')}
      form={{ onSubmit: submit, busy: busy || resolving, submitLabel: t('common.save') }}
      error={error ?? loadError}
    >
      {editing ? (
        <Field label={t('loan.pick')} required error={show('picked')}>
          <AccountPicker ws={ws} value={picked} filterTypes={['loan']} onChange={pick} />
        </Field>
      ) : (
        <>
          <Field label={t('loan.name')} required error={show('name')}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-autofocus />
          </Field>
          <Field label={t('loan.institution')} hint={t('form.optional')}>
            <Input value={institution} onChange={(e) => setInstitution(e.target.value)} maxLength={80} />
          </Field>
          <Field label={t('common.currency')} required error={show('currency')}>
            <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
          </Field>
          <Field label={t('loan.owed')} required error={show('owed')}>
            <MoneyInput value={owed} onChange={setOwed} currency={cur} />
          </Field>
          <Field label={t('loan.principal')} hint={t('form.optional')} error={show('principal')}>
            <MoneyInput value={principal} onChange={setPrincipal} currency={cur} />
          </Field>
          <Field label={t('loan.start')} error={show('start')}>
            <DateField value={start} onChange={setStart} todayYesterdayChips={false} />
          </Field>
        </>
      )}
      <Field label={t('card.apr_percent')} hint={t('form.optional')} error={show('apr')}>
        <Input inputMode="decimal" value={apr} onChange={(e) => setApr(e.target.value.replace(/[^\d.]/g, ''))} placeholder="12.9" />
      </Field>
      <Field label={t('loan.months')} required={!editing} error={show('months')}>
        <Input inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value.replace(/\D/g, ''))} />
      </Field>
    </Dialog>
  );
}

/* -------------------------------------------------------------------- MSI */

export interface MsiDialogProps {
  ws: string;
  /** The card row id (`card-…`), not the pf account id. */
  cardId: string;
  currency: string;
  onClose: Close;
}

export function MsiDialog({ ws, cardId, currency, onClose }: MsiDialogProps) {
  const { t } = useI18n();
  const { busy, error, touched, setTouched, run } = useForm(onClose, t('msi.saved'));
  const [purchase, setPurchase] = useState('');
  const [amount, setAmount] = useState('');
  const [months, setMonths] = useState('12');
  const [started, setStarted] = useState('');
  const [paidMonths, setPaidMonths] = useState('0');
  useEffect(() => setStarted((s) => s || todayLocalIso()), []);

  const errors = {
    purchase: v.required(purchase),
    amount: v.decimal(amount, { positive: true }),
    months: v.integer(months, 1, 120),
    started: v.isoDate(started),
    paid_months: v.integer(paidMonths, 0, 120),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    void run(() =>
      createMsi(ws, cardId, {
        card_id: cardId,
        purchase: purchase.trim(),
        amount: amount.trim(),
        currency,
        months: Number(months),
        started: started.trim(),
        paid_months: Number(paidMonths),
      }),
    );
  };

  return (
    <Dialog open onClose={() => onClose(false)} title={t('msi.new')} form={{ onSubmit: submit, busy, submitLabel: t('common.save') }} error={error}>
      <Field label={t('msi.purchase')} required error={show('purchase')}>
        <Input value={purchase} onChange={(e) => setPurchase(e.target.value)} maxLength={120} data-autofocus />
      </Field>
      <Field label={t('msi.amount')} required error={show('amount')}>
        <MoneyInput value={amount} onChange={setAmount} currency={currency} />
      </Field>
      <Field label={t('msi.months')} required error={show('months')}>
        <Input inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value.replace(/\D/g, ''))} />
      </Field>
      <Field label={t('msi.started')} required error={show('started')}>
        <DateField value={started} onChange={setStarted} />
      </Field>
      <Field label={t('msi.paid_months')} required error={show('paid_months')}>
        <Input inputMode="numeric" value={paidMonths} onChange={(e) => setPaidMonths(e.target.value.replace(/\D/g, ''))} />
      </Field>
    </Dialog>
  );
}

/* ----------------------------------------------------------------- scores */

export function ScoreDialog({ ws, onClose }: { ws: string; onClose: Close }) {
  const { t } = useI18n();
  const { busy, error, touched, setTouched, run } = useForm(onClose, t('score.saved'));
  const [bureau, setBureau] = useState('Buró de Crédito');
  const [score, setScore] = useState('');
  const [date, setDate] = useState('');
  useEffect(() => setDate((d) => d || todayLocalIso()), []);

  const errors = {
    bureau: v.required(bureau),
    score: v.integer(score, 300, 900),
    date: v.isoDate(date),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    void run(() => createScore(ws, { bureau: bureau.trim(), score: Number(score), date: date.trim() }));
  };

  return (
    <Dialog open onClose={() => onClose(false)} title={t('score.new')} form={{ onSubmit: submit, busy, submitLabel: t('common.save') }} error={error}>
      <Field label={t('score.bureau')} required error={show('bureau')}>
        <Input value={bureau} onChange={(e) => setBureau(e.target.value)} maxLength={80} />
      </Field>
      <Field label={t('score.score')} required error={show('score')}>
        <Input inputMode="numeric" value={score} onChange={(e) => setScore(e.target.value.replace(/\D/g, ''))} placeholder="720" data-autofocus />
      </Field>
      <Field label={t('common.date')} required error={show('date')}>
        <DateField value={date} onChange={setDate} />
      </Field>
    </Dialog>
  );
}
