'use client';

/**
 * `AccountForm` — the one account form.
 *
 * Props: `{ws, inline?, onSaved(account), onCancel?}` plus the additive `account` for
 * edit mode. It owns its `<form>` and its footer (primary 'Guardar cuenta' with `loading`,
 * ghost Cancelar when `onCancel` is given); `inline` drops the heading and the wizard embeds
 * it as the step's only primary. The page wraps it in a `Dialog` WITHOUT
 * form mode so there is never a nested form.
 *
 * Liability rule: for a card or a loan the person types what they OWE as a positive
 * number and the value goes out verbatim as `opening_balance` — the server negates, so there is
 * no sign hint here. APR is collected as a percent and sent as `apr_percent`, never `apr`,
 * never divided.
 *
 * Edit mode: `AccountUpdate` (aurum/pf/accounts_admin.py) has no `opening_balance`,
 * `opening_date`, `currency` or `type`, so those render read-only with a hint pointing at
 * Ajustar saldo, and the PUT carries only the editable fields. A 409 (duplicate name) becomes
 * an inline error on Nombre; every other failure is printed under the footer.
 *
 * Type, name and "¿Cuánto tienes hoy?" are on screen; institution, currency, the
 * balance date and the card / loan details sit behind "Más opciones" (open when editing).
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Button, DateField, Field, Input, MoneyInput, MoreOptions, Select } from '@/components/ui';
import { ApiError, createPfAccount, errorMessage, updatePfAccount } from '@/lib/api';
import { todayLocalIso } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Amount } from '@/lib/types';
import type { PfAccount, PfAccountInput, PfAccountType } from '@/lib/types-personal';
import { CURRENCY_RE, DECIMAL_RE, POSITIVE_DECIMAL_RE } from '@/lib/validate';
import { AccountTypeTiles } from './AccountTypeTiles';

export interface AccountFormProps {
  ws: string;
  inline?: boolean;
  /** Edit mode (additive): prefills from the row; type/currency/opening balance are read-only. */
  account?: PfAccount | null;
  onSaved: (account: PfAccount) => void;
  onCancel?: () => void;
}

const LIABILITY: PfAccountType[] = ['credit_card', 'loan'];
const COMMON_CURRENCIES = ['MXN', 'USD', 'EUR'];
const OTHER = '__other__';
const DAYS = Array.from({ length: 31 }, (_, i) => String(i + 1));

/** `'12.5'` → ok; `'abc'` → error key. Positive-only for the amounts a person types here. */
const amountError = (s: string, required: boolean): 'v.required' | 'v.amount' | null => {
  const v = s.trim();
  if (!v) return required ? 'v.required' : null;
  return POSITIVE_DECIMAL_RE.test(v) ? null : 'v.amount';
};
const rateError = (s: string): 'v.amount' | null => (s.trim() && !DECIMAL_RE.test(s.trim()) ? 'v.amount' : null);
const monthsError = (s: string): 'v.amount_positive' | null =>
  s.trim() && !/^[1-9]\d{0,3}$/.test(s.trim()) ? 'v.amount_positive' : null;

export function AccountForm({ ws, inline, account, onSaved, onCancel }: AccountFormProps) {
  const { t } = useI18n();
  const { base } = useMoney();
  const editing = Boolean(account);

  const [type, setType] = useState<PfAccountType>(account?.type ?? 'checking');
  const [name, setName] = useState(account?.name ?? '');
  const [institution, setInstitution] = useState(account?.institution ?? '');
  const initialCurrency = (account?.currency ?? base).toUpperCase();
  const [currencyChoice, setCurrencyChoice] = useState(initialCurrency);
  const [customCurrency, setCustomCurrency] = useState('');
  const [balance, setBalance] = useState(account?.opening_balance?.amount ?? '');
  // The clock is read after mount (design-system §2: nothing prerenders `new Date()`).
  const [date, setDate] = useState(account?.opening_date ?? '');
  const [limit, setLimit] = useState(account?.credit_limit?.amount ?? '');
  const [cutDay, setCutDay] = useState(account?.cut_day ? String(account.cut_day) : '');
  const [dueDay, setDueDay] = useState(account?.due_day ? String(account.due_day) : '');
  const [aprPercent, setAprPercent] = useState(account?.apr_percent ?? '');
  const [loanMonths, setLoanMonths] = useState(account?.loan_months ? String(account.loan_months) : '');
  const [principal, setPrincipal] = useState(account?.loan_principal?.amount ?? '');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);

  useEffect(() => {
    if (!date) setDate(todayLocalIso());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once: seed today after mount
  }, []);

  const currencyOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const c of [base.toUpperCase(), ...COMMON_CURRENCIES, initialCurrency]) {
      if (!seen.has(c)) {
        seen.add(c);
        out.push(c);
      }
    }
    return out;
  }, [base, initialCurrency]);

  const currency = currencyChoice === OTHER ? customCurrency.trim().toUpperCase() : currencyChoice;
  const isLiability = LIABILITY.includes(type);
  const isCard = type === 'credit_card';
  const isLoan = type === 'loan';

  const errors = {
    name: name.trim() ? null : ('v.name_short' as const),
    currency: CURRENCY_RE.test(currency) ? null : ('v.currency' as const),
    balance: editing ? null : amountError(balance, false),
    date: editing ? null : date ? null : ('v.date' as const),
    limit: isCard ? amountError(limit, false) : null,
    apr: isCard || isLoan ? rateError(aprPercent) : null,
    months: isLoan ? monthsError(loanMonths) : null,
    principal: isLoan ? amountError(principal, false) : null,
  };
  const valid = Object.values(errors).every((e) => e === null);
  const show = (key: keyof typeof errors) => (touched && errors[key] ? t(errors[key]) : null);

  const money = (s: string): Amount | null => (s.trim() ? { amount: s.trim(), currency } : null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setNameError(null);
    setError(null);
    if (!valid || busy) return;
    setBusy(true);
    try {
      let saved: PfAccount;
      if (account) {
        // PUT only what `AccountUpdate` accepts (opening balance/date/currency/type are ignored
        // by the server, silently — so they are never sent).
        const body: Partial<PfAccountInput> = {
          name: name.trim(),
          institution: institution.trim() || null,
        };
        if (isCard) {
          body.credit_limit = money(limit);
          body.cut_day = cutDay ? Number(cutDay) : null;
          body.due_day = dueDay ? Number(dueDay) : null;
          body.apr_percent = aprPercent.trim() || null;
        }
        if (isLoan) {
          body.apr_percent = aprPercent.trim() || null;
          body.loan_months = loanMonths.trim() ? Number(loanMonths) : null;
          body.loan_principal = money(principal);
        }
        saved = await updatePfAccount(ws, account.id, body);
      } else {
        const body: PfAccountInput = {
          name: name.trim(),
          type,
          institution: institution.trim() || null,
          currency,
          // Liabilities are typed positive (what is owed); the server negates on write.
          opening_balance: money(balance),
          opening_date: date || todayLocalIso(),
        };
        if (isCard) {
          body.credit_limit = money(limit);
          body.cut_day = cutDay ? Number(cutDay) : null;
          body.due_day = dueDay ? Number(dueDay) : null;
          body.apr_percent = aprPercent.trim() || null;
        }
        if (isLoan) {
          body.apr_percent = aprPercent.trim() || null;
          body.loan_months = loanMonths.trim() ? Number(loanMonths) : null;
          body.loan_principal = money(principal);
        }
        saved = await createPfAccount(ws, body);
      }
      onSaved(saved);
    } catch (err) {
      // The duplicate-name 409 maps to `code 'budget_exists'` through the regex table, so the
      // branch is on the status, never on the code.
      if (err instanceof ApiError && err.status === 409) setNameError(t('acct.name.dup'));
      else setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const balanceLabel = isLiability ? t('acct.owed_today') : t('acct.have_today');
  const balanceHint = editing ? t('acct.opening.locked') : isLiability ? t('acct.owed_today.hint') : t('acct.have_today.hint');

  const daySelect = (value: string, onChange: (v: string) => void, testId: string) => (
    <Select value={value} onChange={(e) => onChange(e.target.value)} disabled={busy} data-testid={testId}>
      <option value="">—</option>
      {DAYS.map((d) => (
        <option key={d} value={d}>
          {d}
        </option>
      ))}
    </Select>
  );

  const rateField = (
    <Field label={t('acct.apr')} error={show('apr')}>
      <Input
        inputMode="decimal"
        value={aprPercent}
        onChange={(e) => setAprPercent(e.target.value)}
        disabled={busy}
        data-testid="acct-apr"
      />
    </Field>
  );

  return (
    <form
      className="stack"
      onSubmit={(e) => void submit(e)}
      aria-busy={busy || undefined}
      noValidate
      data-testid="acct-form"
    >
      {!inline && !editing && <h3>{t('acct.type.pick')}</h3>}
      {!editing && <AccountTypeTiles value={type} onChange={setType} disabled={busy} />}

      <Field label={t('acct.name')} hint={t('acct.name.hint')} error={nameError ?? show('name')} required>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
          autoComplete="off"
          maxLength={80}
          data-autofocus
          data-testid="acct-name"
        />
      </Field>
      <Field label={balanceLabel} hint={balanceHint} error={show('balance')}>
        <MoneyInput
          value={balance}
          onChange={setBalance}
          currency={currency || base}
          allowNegative={false}
          disabled={busy || editing}
          name="opening_balance"
        />
      </Field>
      <MoreOptions defaultOpen={editing}>
        <Field label={t('acct.institution')}>
          <Input value={institution} onChange={(e) => setInstitution(e.target.value)} disabled={busy} maxLength={80} />
        </Field>
        <Field label={t('acct.currency')} error={show('currency')}>
          <Select
            value={currencyChoice}
            onChange={(e) => setCurrencyChoice(e.target.value)}
            disabled={busy || editing}
            data-testid="acct-currency"
          >
            {currencyOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            {!editing && <option value={OTHER}>{t('acct.currency.other')}</option>}
          </Select>
        </Field>
        {currencyChoice === OTHER && (
          <Field label={t('acct.currency.code')} error={show('currency')} required>
            <Input
              value={customCurrency}
              onChange={(e) => setCustomCurrency(e.target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3))}
              maxLength={3}
              autoCapitalize="characters"
              disabled={busy}
              data-testid="acct-currency-code"
            />
          </Field>
        )}

        <Field label={t('acct.opening_date')} error={show('date')}>
          <DateField value={date} onChange={setDate} disabled={busy || editing} todayYesterdayChips={!editing} />
        </Field>

        {isCard && (
          <fieldset className="fieldset stack">
            <legend>{t('acct.card_fields')}</legend>
            <Field label={t('acct.cut_day')}>{daySelect(cutDay, setCutDay, 'acct-cut-day')}</Field>
            <Field label={t('acct.due_day')}>{daySelect(dueDay, setDueDay, 'acct-due-day')}</Field>
            <Field label={t('acct.credit_limit')} error={show('limit')}>
              <MoneyInput value={limit} onChange={setLimit} currency={currency || base} disabled={busy} name="credit_limit" />
            </Field>
            {rateField}
          </fieldset>
        )}

        {isLoan && (
          <fieldset className="fieldset stack">
            <legend>{t('acct.loan_fields')}</legend>
            {rateField}
            <Field label={t('acct.loan.term_label')} error={show('months')}>
              <Input
                inputMode="numeric"
                value={loanMonths}
                onChange={(e) => setLoanMonths(e.target.value.replace(/\D/g, ''))}
                disabled={busy}
                data-testid="acct-loan-months"
              />
            </Field>
            <Field label={t('acct.loan.principal')} error={show('principal')}>
              <MoneyInput value={principal} onChange={setPrincipal} currency={currency || base} disabled={busy} name="loan_principal" />
            </Field>
          </fieldset>
        )}
      </MoreOptions>

      {error && (
        <p className="ui-dialog-error" role="alert">
          {error}
        </p>
      )}

      <div className="row">
        <Button type="submit" variant="primary" loading={busy} data-testid="acct-save">
          {t('acct.save')}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
        )}
      </div>
    </form>
  );
}
