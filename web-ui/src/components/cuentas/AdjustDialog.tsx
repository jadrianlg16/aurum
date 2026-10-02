'use client';

/**
 * `AdjustDialog` — "Ajustar saldo" for when the bank and the app disagree. The person types
 * the real balance today ('Saldo real hoy' for an asset, 'Lo que debes hoy' for a card or a
 * loan — positive, the server signs the delta) and the API posts one adjustment movement;
 * nothing already logged changes.
 *
 * `Dialog` in form mode (Enter submits); the caller toasts and reloads on `onClose(true)`. The
 * amount field is the dialog's `initialFocus`: without it `showModal()` lands on the header ×
 * (the first focusable) and Enter would close the dialog instead of submitting.
 */
import { useEffect, useRef, useState } from 'react';
import { DateField, Dialog, Field, Input, MoneyInput } from '@/components/ui';
import { adjustPfAccount, errorMessage } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { PfAccount } from '@/lib/types-personal';
import { DECIMAL_RE, POSITIVE_DECIMAL_RE } from '@/lib/validate';
import { useOpenAfterMount } from './useOpenAfterMount';

export interface AdjustDialogProps {
  ws: string;
  account: PfAccount;
  open: boolean;
  onClose: (saved: boolean) => void;
}

export function AdjustDialog({ ws, account, open, onClose }: AdjustDialogProps) {
  const { t } = useI18n();
  const { base } = useMoney();
  const owed = Boolean(account.owed);
  const currency = (account.currency ?? base).toUpperCase();

  const [balance, setBalance] = useState(account.balance?.amount ?? '');
  const [date, setDate] = useState('');
  const [note, setNote] = useState('');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = useOpenAfterMount(open);
  const balanceRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setBalance(account.balance?.amount ?? '');
      setDate(todayLocalIso());
      setNote('');
      setTouched(false);
      setError(null);
    }
  }, [open, account.id, account.balance?.amount]);

  const re = owed ? POSITIVE_DECIMAL_RE : DECIMAL_RE;
  const balanceError = balance.trim() ? (re.test(balance.trim()) ? null : 'v.amount') : 'v.required';
  const dateError = date ? null : 'v.date';

  const submit = async () => {
    setTouched(true);
    if (balanceError || dateError || busy) return;
    setBusy(true);
    setError(null);
    try {
      await adjustPfAccount(ws, account.id, {
        balance: { amount: balance.trim(), currency },
        date,
        note: note.trim() || null,
      });
      onClose(true);
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={shown}
      onClose={() => onClose(false)}
      title={`${t('acct.adjust.title')} — ${account.name}`}
      description={t('acct.adjust.explain')}
      size="sm"
      form={{ onSubmit: () => void submit(), busy, submitLabel: t('acct.adjust') }}
      error={error}
      initialFocus={balanceRef}
    >
      <div className="stack">
        <Field label={owed ? t('acct.adjust.owed') : t('acct.adjust.balance')} error={touched && balanceError ? t(balanceError) : null} required>
          <MoneyInput ref={balanceRef} value={balance} onChange={setBalance} currency={currency} allowNegative={!owed} disabled={busy} name="balance" />
        </Field>
        <Field label={t('acct.adjust.date')} error={touched && dateError ? t(dateError) : null} required>
          <DateField value={date} onChange={setDate} disabled={busy} />
        </Field>
        <Field label={t('acct.adjust.note')}>
          <Input value={note} onChange={(e) => setNote(e.target.value)} disabled={busy} maxLength={200} />
        </Field>
      </div>
    </Dialog>
  );
}
