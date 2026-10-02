'use client';

/**
 * Create / edit a goal. The body is exactly
 * `{kind, name, target, target_date?, account_id}` — the account is a pf account id picked from
 * `AccountPicker`, never a ledger string, and there is no currency field: the server derives both
 * from the account. `target` is sent as the decimal string typed in `MoneyInput` (the
 * server's `Goal.target` input is a `str`).
 *
 * Templates prefill only: `emergency` = kind + name + target = the sum of the last three
 * months' expenses (`GET /review/{period}` × 3, summed with `sumDecimals` — three times the
 * average of three months is their sum, so nothing is divided); `trip` = kind purchase + name.
 * A past `target_date` is refused by the server with a 422 on that field → inline error; the
 * date field's `min` is computed in an effect (no Date at prerender).
 */
import { useEffect, useState } from 'react';
import { AccountPicker, DateField, Dialog, Field, Icon, Input, MoneyInput, useToast } from '@/components/ui';
import { ApiError, createGoal, errorMessage, getReview, updateGoal } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { currentPeriod, shiftPeriod } from '@/lib/period';
import { sumDecimals } from '@/lib/validate';
import * as v from '@/lib/validate';
import { useWorkspace } from '@/lib/workspace';
import type { Goal, GoalCreate, GoalKind } from '@/lib/types';
import type { PfAccount, PfAccountType } from '@/lib/types-personal';
import { GOAL_ICON, goalTargetString } from './GoalCard';
import styles from './GoalDialog.module.css';

export type GoalTemplate = 'emergency' | 'trip';

const KINDS: GoalKind[] = ['savings', 'emergency', 'debt', 'purchase'];
const SAVING_TYPES: PfAccountType[] = ['savings', 'investment', 'checking'];
const DEBT_TYPES: PfAccountType[] = ['credit_card', 'loan'];

export interface GoalDialogProps {
  ws: string;
  goal?: Goal | null;
  template?: GoalTemplate;
  onClose: (saved: boolean) => void;
}

export function GoalDialog({ ws, goal, template, onClose }: GoalDialogProps) {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const toast = useToast();
  const editing = Boolean(goal);

  const [kind, setKind] = useState<GoalKind>(goal?.kind ?? (template === 'emergency' ? 'emergency' : template === 'trip' ? 'purchase' : 'savings'));
  const [name, setName] = useState(
    goal?.name ?? (template === 'emergency' ? t('goal.template.emergency.name') : template === 'trip' ? t('goal.template.trip') : ''),
  );
  const [target, setTarget] = useState(goal ? goalTargetString(goal) : '');
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? '');
  const [accountId, setAccountId] = useState(goal?.account_id ?? '');
  const [account, setAccount] = useState<PfAccount | null>(null);
  const [minDate, setMinDate] = useState<string | undefined>(undefined);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateError, setDateError] = useState<string | null>(null);

  useEffect(() => setMinDate(todayLocalIso()), []);

  // Emergency template: 3 × the average monthly spend of the three months before this one.
  useEffect(() => {
    if (template !== 'emergency' || goal) return undefined;
    let alive = true;
    const now = currentPeriod();
    Promise.all([1, 2, 3].map((n) => getReview(ws, shiftPeriod(now, -n)).catch(() => null)))
      .then((reviews) => {
        if (!alive) return;
        const amounts = reviews.map((r) => r?.expense?.amount).filter((a): a is string => typeof a === 'string' && v.DECIMAL_RE.test(a));
        if (amounts.length === 0) return;
        const sum = sumDecimals(amounts).replace(/^-/, '');
        setTarget((cur) => (cur ? cur : sum));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [ws, template, goal]);

  const currency = (account?.currency ?? current?.base_currency ?? goal?.currency ?? 'MXN').toUpperCase();
  const isDebt = kind === 'debt';
  // Switching between a saving kind and debt changes the account filter, so the pick is cleared.
  const pickKind = (k: GoalKind) => {
    if (k === kind) return;
    setKind(k);
    if ((k === 'debt') !== isDebt) {
      setAccountId('');
      setAccount(null);
    }
  };

  const errors = {
    name: v.required(name),
    target: v.decimal(target, { positive: true }),
    account_id: v.required(accountId),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = async () => {
    setTouched(true);
    setDateError(null);
    if (!v.isValid(errors)) return;
    setBusy(true);
    setError(null);
    const body: GoalCreate = {
      kind,
      name: name.trim(),
      target: target.trim(),
      account_id: accountId,
    };
    if (targetDate.trim()) body.target_date = targetDate.trim();
    else if (goal?.target_date) body.target_date = null;
    try {
      if (goal) await updateGoal(ws, goal.id, body);
      else await createGoal(ws, body);
      onClose(true);
      toast.success(t('goal.saved'));
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.field === 'target_date') setDateError(errorMessage(e, t));
      else setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={editing ? t('goal.edit') : t('goal.new')}
      form={{ onSubmit: () => void submit(), busy, submitLabel: t('common.save') }}
      error={error}
    >
      <Field label={t('goal.kind')} asGroup>
        <div className={styles.tiles} role="radiogroup" aria-label={t('goal.kind')}>
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              className={styles.tile}
              aria-checked={kind === k}
              tabIndex={kind === k ? 0 : -1}
              data-testid={`goal-kind-${k}`}
              onClick={() => pickKind(k)}
              onKeyDown={(e) => {
                const delta = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
                if (!delta) return;
                e.preventDefault();
                const next = KINDS[(KINDS.indexOf(kind) + delta + KINDS.length) % KINDS.length];
                pickKind(next);
                (e.currentTarget.parentElement?.querySelector(`[data-testid="goal-kind-${next}"]`) as HTMLButtonElement | null)?.focus();
              }}
            >
              <Icon name={GOAL_ICON[k]} size={18} />
              {t(`goal.type.${k}`)}
            </button>
          ))}
        </div>
      </Field>
      <Field label={t('goal.name')} required error={show('name')}>
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-autofocus />
      </Field>
      <Field label={t('goal.target_amount')} hint={t('goal.target_amount.hint')} required error={show('target')}>
        <MoneyInput value={target} onChange={setTarget} currency={currency} />
      </Field>
      <Field label={t('goal.by_when')} hint={t('goal.by_when.hint')} error={dateError}>
        <DateField value={targetDate} onChange={setTargetDate} todayYesterdayChips={false} min={minDate} />
      </Field>
      <Field label={isDebt ? t('goal.debt_account') : t('goal.account')} hint={t('goal.account.hint')} required error={show('account_id')}>
        <AccountPicker
          ws={ws}
          value={accountId}
          filterTypes={isDebt ? DEBT_TYPES : SAVING_TYPES}
          onChange={(id, a) => {
            setAccountId(id);
            setAccount(a);
          }}
        />
      </Field>
    </Dialog>
  );
}
