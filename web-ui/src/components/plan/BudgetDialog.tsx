'use client';

/**
 * Create / edit one budget. The body is exactly
 * `{label_id, period, amount, currency, rollover}`: no tax or deductible field, no repeat flag and
 * no client fan-out — carrying a budget into the next month is the server's `budgets/copy`.
 * `currency` is the workspace's base currency (the picker shows it as a chip). A 409 from the
 * server lands on the category field as `err.budget_exists`.
 */
import { useState } from 'react';
import tap from '@/components/plan/tap.module.css';
import { CategoryPicker, Dialog, Field, MoneyInput, MonthPicker, useToast } from '@/components/ui';
import { ApiError, createBudget, errorMessage, updateBudget } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useWorkspace } from '@/lib/workspace';
import * as v from '@/lib/validate';
import type { BudgetStatusRow } from '@/lib/types';

export interface BudgetDialogProps {
  ws: string;
  period: string;
  /** Present when editing a row of `/budgets/status`. */
  budget?: BudgetStatusRow | null;
  onClose: (saved: boolean) => void;
}

export function BudgetDialog({ ws, period, budget, onClose }: BudgetDialogProps) {
  const { t } = useI18n();
  const { current } = useWorkspace();
  const toast = useToast();
  const currency = (current?.base_currency ?? budget?.budget.currency ?? 'MXN').toUpperCase();
  const editing = Boolean(budget);

  const [labelId, setLabelId] = useState(budget?.label_id ?? '');
  const [month, setMonth] = useState(period);
  const [amount, setAmount] = useState(budget?.budget.amount ?? '');
  const [rollover, setRollover] = useState(Boolean(budget?.rollover));
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labelError, setLabelError] = useState<string | null>(null);

  const errors = {
    label_id: v.required(labelId),
    amount: v.decimal(amount, { positive: true }),
  };
  const show = (k: keyof typeof errors) => (touched && errors[k] ? t(errors[k]) : null);

  const submit = async () => {
    setTouched(true);
    setLabelError(null);
    if (!v.isValid(errors)) return;
    setBusy(true);
    setError(null);
    const body = { label_id: labelId, period: month, amount: amount.trim(), currency, rollover };
    try {
      if (budget) await updateBudget(ws, budget.budget_id, body);
      else await createBudget(ws, body);
      onClose(true);
      toast.success(t('budget.saved'));
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'budget_exists' || e.status === 409)) {
        setLabelError(t('err.budget_exists'));
      } else {
        setError(errorMessage(e, t));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      onClose={() => onClose(false)}
      title={editing ? t('budget.edit') : t('budget.new')}
      form={{ onSubmit: () => void submit(), busy, submitLabel: t('common.save') }}
      error={error}
    >
      <Field label={t('budget.category')} required error={labelError ?? show('label_id')}>
        <CategoryPicker
          ws={ws}
          kind="expense"
          value={labelId}
          onChange={(id) => setLabelId(id)}
          allowNew={!editing}
          disabled={editing}
        />
      </Field>
      <Field label={t('budget.amount')} required error={show('amount')}>
        <MoneyInput value={amount} onChange={setAmount} currency={currency} />
      </Field>
      <Field label={t('budget.month')} asGroup>
        <MonthPicker value={month} onChange={setMonth} />
      </Field>
      <label className={tap.choice}>
        <input type="checkbox" checked={rollover} onChange={(e) => setRollover(e.target.checked)} />
        <span>{t('budget.carry')}</span>
      </label>
    </Dialog>
  );
}
