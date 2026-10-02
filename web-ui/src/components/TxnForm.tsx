'use client';

/**
 * Manual transaction editor (Libros → "Nueva transacción").
 *
 * The postings editor enforces Beancount's own rule, client-side, before the request goes out:
 * at least two postings, and **at most one** posting may leave its amount blank — that one is
 * the balancing leg the engine fills in (`aurum/ledger/base.py::Transaction.balanced`). When
 * every amount is filled, the sum must be exactly zero; the check runs in integer centavos
 * (`lib/validate.sumDecimals`), never in floating point, and the API re-checks it anyway.
 *
 * Create → `POST /ledger/{ws}/transactions`. Edit → `PUT .../{txn_id}` and void →
 * `DELETE .../{txn_id}`; a transaction with no link/id cannot be addressed, so
 * the screen says so instead of guessing an id.
 */
import { useState } from 'react';
import { createTransaction, errorMessage, updateTransaction, voidTransaction } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import * as v from '@/lib/validate';
import type { Posting, Transaction } from '@/lib/types';
import { Money } from './Bits';
import { AccountField, DecimalField, Dialog, TextField } from './Form';
import { PostingTable } from './Posting';

interface PostingDraft {
  account: string;
  amount: string;
  currency: string;
}

const blankPosting = (currency: string): PostingDraft => ({ account: '', amount: '', currency });

function toDraft(p: Posting, fallbackCurrency: string): PostingDraft {
  return {
    account: p.account,
    amount: p.amount?.amount ?? '',
    currency: p.amount?.currency ?? fallbackCurrency,
  };
}

/** The transaction as it will be sent — the same object the preview renders. */
function buildTxn(
  date: string,
  payee: string,
  narration: string,
  tags: string,
  postings: PostingDraft[],
  meta: Record<string, string>,
  links: string[],
): Transaction {
  return {
    date: date.trim(),
    payee: payee.trim() || null,
    narration: narration.trim(),
    postings: postings.map((p) => ({
      account: p.account.trim(),
      amount: p.amount.trim()
        ? { amount: p.amount.trim(), currency: p.currency.trim().toUpperCase() }
        : null,
    })),
    tags: tags
      .split(',')
      .map((s) => s.trim().replace(/^#/, ''))
      .filter(Boolean),
    links,
    meta,
  };
}

export function TransactionDialog({
  ws,
  accounts,
  baseCurrency = 'MXN',
  txn,
  txnId,
  onClose,
}: {
  ws: string;
  accounts: string[];
  baseCurrency?: string;
  /** Present when editing an existing transaction. */
  txn?: Transaction | null;
  /** The id the API addresses it by (its first Beancount link). */
  txnId?: string | null;
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [date, setDate] = useState(txn?.date ?? new Date().toISOString().slice(0, 10));
  const [payee, setPayee] = useState(txn?.payee ?? '');
  const [narration, setNarration] = useState(txn?.narration ?? '');
  const [tags, setTags] = useState((txn?.tags ?? []).join(', '));
  const [postings, setPostings] = useState<PostingDraft[]>(
    txn ? txn.postings.map((p) => toDraft(p, baseCurrency)) : [blankPosting(baseCurrency), blankPosting(baseCurrency)],
  );
  const [touched, setTouched] = useState(false);

  const editing = Boolean(txn);
  const setPosting = (i: number, patch: Partial<PostingDraft>) =>
    setPostings((ps) => ps.map((p, j) => (i === j ? { ...p, ...patch } : p)));

  const blanks = postings.filter((p) => !p.amount.trim()).length;
  const filled = postings.filter((p) => p.amount.trim());
  const residual = v.sumDecimals(filled.map((p) => p.amount));
  const balanced = blanks === 1 || (blanks === 0 && v.isZero(residual));

  const errors: Record<string, v.FieldError> = {
    date: v.isoDate(date),
    narration: v.required(narration),
    count: postings.length >= 2 ? null : 'valid.min_postings',
    blanks: blanks <= 1 ? null : 'valid.one_blank',
    balance: balanced ? null : 'valid.unbalanced',
  };
  postings.forEach((p, i) => {
    errors[`account${i}`] = v.account(p.account);
    errors[`amount${i}`] = p.amount.trim() ? v.decimal(p.amount, { positive: false }) : null;
    errors[`currency${i}`] = p.amount.trim() ? v.currency(p.currency) : null;
  });
  const show = (k: string) => (touched ? errors[k] ?? null : null);

  const draft = buildTxn(date, payee, narration, tags, postings, txn?.meta ?? { source: 'manual' }, txn?.links ?? []);

  const submit = () => {
    setTouched(true);
    if (!v.isValid(errors)) return;
    setBusy(true);
    setApiError(null);
    const call =
      editing && txnId ? updateTransaction(ws, txnId, draft) : createTransaction(ws, draft);
    call
      .then(() => onClose(true))
      .catch((e) => setApiError(errorMessage(e)))
      .finally(() => setBusy(false));
  };

  return (
    <Dialog
      title={editing ? t('txn.edit') : t('txn.new')}
      onCancel={() => onClose(false)}
      onSubmit={submit}
      busy={busy}
      error={apiError}
      submitLabel={t('txn.submit')}
      wide
    >
      {editing && !txnId && <p className="banner warn">{t('txn.no_id')}</p>}
      <div className="grid cols-3">
        <TextField label={t('common.date')} type="date" value={date} onChange={setDate} error={show('date')} required />
        <TextField label={t('common.payee')} value={payee ?? ''} onChange={setPayee} hint={t('form.optional')} />
        <TextField label={t('txn.narration')} value={narration} onChange={setNarration} error={show('narration')} required />
      </div>
      <TextField label={t('txn.tags')} value={tags} onChange={setTags} hint={t('form.optional')} />

      <h3 style={{ marginTop: 10 }}>{t('txn.postings')}</h3>
      <p className="small muted">{t('txn.blank_hint')}</p>
      {postings.map((p, i) => (
        <div key={i} className="grid cols-4" style={{ alignItems: 'start', gap: 8 }}>
          <AccountField
            label={t('common.account')}
            value={p.account}
            onChange={(x) => setPosting(i, { account: x })}
            accounts={accounts}
            error={show(`account${i}`)}
            required
          />
          <DecimalField
            label={t('common.amount')}
            value={p.amount}
            onChange={(x) => setPosting(i, { amount: x })}
            error={show(`amount${i}`)}
            allowNegative
            placeholder="—"
          />
          <TextField
            label={t('ws.currency')}
            value={p.currency}
            onChange={(x) => setPosting(i, { currency: x })}
            error={show(`currency${i}`)}
          />
          <div style={{ paddingTop: 22 }}>
            <button
              type="button"
              className="btn ghost"
              disabled={postings.length <= 2}
              onClick={() => setPostings((ps) => ps.filter((_, j) => j !== i))}
            >
              {t('txn.remove_posting')}
            </button>
          </div>
        </div>
      ))}
      <div className="row" style={{ marginBottom: 10 }}>
        <button type="button" className="btn" onClick={() => setPostings((ps) => [...ps, blankPosting(baseCurrency)])}>
          {t('txn.add_posting')}
        </button>
        <div style={{ flex: 1 }} />
        {balanced ? (
          <span className="badge pos">{t('txn.balanced')}</span>
        ) : (
          <span className="badge neg">
            {t('txn.balance')} <Money value={{ amount: residual, currency: baseCurrency }} sign />
          </span>
        )}
      </div>
      {show('count') && <p className="err small">{t('valid.min_postings')}</p>}
      {show('blanks') && <p className="err small">{t('valid.one_blank')}</p>}
      {show('balance') && <p className="err small">{t('valid.unbalanced')}</p>}

      <h3>{t('txn.preview')}</h3>
      <div className="card">
        <PostingTable txn={draft} />
      </div>
    </Dialog>
  );
}

/** Void confirmation: `DELETE /ledger/{ws}/transactions/{id}`. */
export function VoidTransactionDialog({
  ws,
  txnId,
  narration,
  onClose,
}: {
  ws: string;
  txnId: string;
  narration: string;
  onClose: (saved: boolean) => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    setBusy(true);
    setError(null);
    voidTransaction(ws, txnId)
      .then(() => onClose(true))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setBusy(false));
  };
  return (
    <Dialog
      title={t('txn.void')}
      onCancel={() => onClose(false)}
      onSubmit={submit}
      busy={busy}
      error={error}
      destructive
      submitLabel={t('txn.void')}
    >
      <p>{narration}</p>
      <p className="notice">{t('txn.void_confirm')}</p>
    </Dialog>
  );
}
