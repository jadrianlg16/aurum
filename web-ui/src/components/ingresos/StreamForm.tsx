'use client';

/**
 * `StreamForm` — the one income form: "me pagan el 15 y el 30".
 *
 * Props `{ws, inline?, template?, onSaved(stream)}` plus the additive `stream` (edit)
 * and `onCancel`. A bare `<form>` with its own primary 'Guardar ingreso';
 * the page's Dialog never uses form mode around it (no nested form).
 *
 * Wire shape (aurum/pf/streams.py): `anchor_days` only for monthly/semimonthly, else `[]`
 * (never null — a 422 on POST, 400 on PUT); `weekday` only for weekly/biweekly, else null,
 * with 0 = Monday (Python `date.weekday()`), so the names are built from a known Monday and
 * `Intl.DateTimeFormat(lang, {weekday: 'long'})`. `31` is "último día". Templates prefill
 * (salary_semimonthly = salary + [15, 31]; salary_monthly = salary + [30]; freelance =
 * freelance + irregular). Edit uses `updateStream` with the full form (the server merges).
 *
 * Name, amount, how often, which days and the account (auto-picked) are on screen;
 * the income type, category, gross amount, notes and — on create — "sigue llegando" sit behind
 * "Más opciones".
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  AccountPicker,
  Button,
  CategoryPicker,
  DateField,
  Field,
  Input,
  MoneyInput,
  MoreOptions,
  Select,
  Textarea,
} from '@/components/ui';
import { createStream, errorMessage, listLabels, updateStream } from '@/lib/api';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Amount } from '@/lib/types';
import type { IncomeStream, IncomeStreamInput, PfAccount, StreamCadence, StreamSourceType } from '@/lib/types-personal';
import { STREAM_CADENCES, STREAM_SOURCE_TYPES } from '@/lib/types-personal';
import { POSITIVE_DECIMAL_RE } from '@/lib/validate';
import styles from '@/components/cuentas/choice.module.css';

export type StreamTemplate = 'salary_semimonthly' | 'salary_monthly' | 'freelance';

export interface StreamFormProps {
  ws: string;
  inline?: boolean;
  template?: StreamTemplate;
  /** Edit mode (additive). */
  stream?: IncomeStream | null;
  onSaved: (stream: IncomeStream) => void;
  onCancel?: () => void;
}

const LAST_DAY = 31;
const NEEDS_DAYS: StreamCadence[] = ['monthly', 'semimonthly'];
const NEEDS_WEEKDAY: StreamCadence[] = ['weekly', 'biweekly'];
const NEEDS_DATE: StreamCadence[] = ['annual', 'irregular'];
const DAYS_1_30 = Array.from({ length: 30 }, (_, i) => i + 1);
const DEFAULT_LABEL_NAME = 'Sueldo/Nómina';

/** Monday-first weekday names (0 = Monday, the organizer convention) in the UI language. */
export function weekdayNames(lang: string): string[] {
  const fmt = new Intl.DateTimeFormat(lang === 'en' ? 'en-US' : 'es-MX', { weekday: 'long' });
  // 2024-01-01 is a Monday; local-date constructor so the weekday never shifts with the zone.
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)));
}

function templateDefaults(template: StreamTemplate | undefined): Partial<{ source: StreamSourceType; cadence: StreamCadence; days: number[] }> {
  switch (template) {
    case 'salary_semimonthly':
      return { source: 'salary', cadence: 'semimonthly', days: [15, LAST_DAY] };
    case 'salary_monthly':
      return { source: 'salary', cadence: 'monthly', days: [30] };
    case 'freelance':
      return { source: 'freelance', cadence: 'irregular', days: [] };
    default:
      return {};
  }
}

export function StreamForm({ ws, inline, template, stream, onSaved, onCancel }: StreamFormProps) {
  const { t, lang } = useI18n();
  const { base } = useMoney();
  const tpl = templateDefaults(template);

  const [name, setName] = useState(stream?.name ?? '');
  const [source, setSource] = useState<StreamSourceType>(stream?.source_type ?? tpl.source ?? 'salary');
  const [accountId, setAccountId] = useState(stream?.account_id ?? '');
  const [account, setAccount] = useState<PfAccount | null>(null);
  const [amount, setAmount] = useState(stream?.amount?.amount ?? '');
  const [gross, setGross] = useState(stream?.gross_amount?.amount ?? '');
  const [labelId, setLabelId] = useState(stream?.label_id ?? '');
  const [labelTouched, setLabelTouched] = useState(Boolean(stream?.label_id));
  const [cadence, setCadence] = useState<StreamCadence>(stream?.cadence ?? tpl.cadence ?? 'semimonthly');
  const [cadenceTouched, setCadenceTouched] = useState(Boolean(stream) || Boolean(tpl.cadence));
  const initialDays = stream?.anchor_days?.length ? stream.anchor_days : tpl.days ?? [15, LAST_DAY];
  const [day1, setDay1] = useState<number>(initialDays[0] ?? 15);
  const [day2, setDay2] = useState<number>(initialDays[1] ?? LAST_DAY);
  const [weekday, setWeekday] = useState<number>(stream?.weekday ?? 4);
  const [nextDate, setNextDate] = useState(stream?.next_expected ?? '');
  const [active, setActive] = useState(stream?.active ?? true);
  const [notes, setNotes] = useState(stream?.notes ?? '');
  const [salaryLabelId, setSalaryLabelId] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The label named exactly 'Sueldo/Nómina' is the default category for a salary (a seeded income category).
  useEffect(() => {
    if (!ws) return undefined;
    let alive = true;
    listLabels(ws, { kind: 'income' })
      .then((rows) => {
        if (!alive) return;
        const hit = (Array.isArray(rows) ? rows : []).find((l) => l.name === DEFAULT_LABEL_NAME);
        setSalaryLabelId(hit?.id ?? null);
      })
      .catch(() => {
        if (alive) setSalaryLabelId(null);
      });
    return () => {
      alive = false;
    };
  }, [ws]);

  // Sueldo defaults to twice a month; anything else to monthly — until the person picks one.
  const pickSource = (s: StreamSourceType) => {
    setSource(s);
    if (!cadenceTouched) setCadence(s === 'salary' ? 'semimonthly' : 'monthly');
  };

  const effectiveLabelId = labelId || (source === 'salary' && !labelTouched && salaryLabelId ? salaryLabelId : '');
  const currency = (account?.currency ?? stream?.amount?.currency ?? base).toUpperCase();
  const weekdays = useMemo(() => weekdayNames(lang), [lang]);

  const errors = {
    name: name.trim() ? null : ('v.name_short' as const),
    account: accountId ? null : ('v.required' as const),
    amount: POSITIVE_DECIMAL_RE.test(amount.trim()) && !/^0(\.0{1,2})?$/.test(amount.trim()) ? null : ('v.amount_positive' as const),
    gross: gross.trim() && !POSITIVE_DECIMAL_RE.test(gross.trim()) ? ('v.amount' as const) : null,
    next: NEEDS_DATE.includes(cadence) && !nextDate ? ('v.date' as const) : null,
  };
  const valid = Object.values(errors).every((e) => e === null);
  const show = (key: keyof typeof errors) => (touched && errors[key] ? t(errors[key]) : null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!valid || busy) return;
    setBusy(true);
    const money = (s: string): Amount => ({ amount: s.trim(), currency });
    const body: IncomeStreamInput = {
      name: name.trim(),
      source_type: source,
      amount: money(amount),
      gross_amount: gross.trim() ? money(gross) : null,
      cadence,
      anchor_days: cadence === 'semimonthly' ? [day1, day2] : cadence === 'monthly' ? [day1] : [],
      weekday: NEEDS_WEEKDAY.includes(cadence) ? weekday : null,
      next_expected: NEEDS_DATE.includes(cadence) ? nextDate || null : null,
      account_id: accountId,
      label_id: effectiveLabelId || null,
      active,
      notes: notes.trim() || null,
    };
    try {
      const saved = stream ? await updateStream(ws, stream.id, body) : await createStream(ws, body);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  // Two selects share one Field group, so each needs its own accessible name (the group label is not enough).
  const daySelect = (value: number, onChange: (d: number) => void, testId: string, ariaLabel: string) => (
    <Select value={String(value)} onChange={(e) => onChange(Number(e.target.value))} disabled={busy} data-testid={testId} aria-label={ariaLabel}>
      {DAYS_1_30.map((d) => (
        <option key={d} value={d}>
          {d}
        </option>
      ))}
      <option value={LAST_DAY}>{t('inc.day.last')}</option>
    </Select>
  );

  // Visible when editing (stopping an income is a real edit); tucked under "Más opciones" on create.
  const activeToggle = (
    <label className="row">
      <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} disabled={busy} data-testid="inc-active" />
      {active ? t('inc.still') : t('inc.stopped')}
    </label>
  );

  return (
    <form className="stack" onSubmit={(e) => void submit(e)} aria-busy={busy || undefined} noValidate data-testid="inc-form" data-inline={inline || undefined}>
      <Field label={t('inc.name')} error={show('name')} required>
        <Input value={name} onChange={(e) => setName(e.target.value)} disabled={busy} maxLength={80} autoComplete="off" data-autofocus data-testid="inc-name" />
      </Field>

      <Field label={t('inc.amount.net')} hint={t('inc.amount.hint')} error={show('amount')} required>
        <MoneyInput value={amount} onChange={setAmount} currency={currency} disabled={busy} name="amount" />
      </Field>

      <Field label={t('inc.cadence')}>
        <Select
          value={cadence}
          onChange={(e) => {
            setCadence(e.target.value as StreamCadence);
            setCadenceTouched(true);
          }}
          disabled={busy}
          data-testid="inc-cadence"
        >
          {STREAM_CADENCES.map((c) => (
            <option key={c} value={c}>
              {t(`inc.cadence.${c}`)}
            </option>
          ))}
        </Select>
      </Field>

      {NEEDS_DAYS.includes(cadence) && (
        <Field label={t('inc.days.q')} asGroup>
          <div className="row">
            {daySelect(day1, setDay1, 'inc-day-1', t('inc.days.first'))}
            {cadence === 'semimonthly' && daySelect(day2, setDay2, 'inc-day-2', t('inc.days.second'))}
          </div>
        </Field>
      )}

      {NEEDS_WEEKDAY.includes(cadence) && (
        <Field label={t('inc.weekday.q')}>
          <Select value={String(weekday)} onChange={(e) => setWeekday(Number(e.target.value))} disabled={busy} data-testid="inc-weekday">
            {weekdays.map((n, i) => (
              <option key={i} value={i}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
      )}

      {NEEDS_DATE.includes(cadence) && (
        <Field label={t('inc.next_expected')} error={show('next')} required>
          <DateField value={nextDate} onChange={setNextDate} disabled={busy} todayYesterdayChips={false} />
        </Field>
      )}

      <Field label={t('inc.account.q')} error={show('account')} required>
        <AccountPicker
          ws={ws}
          value={accountId}
          autoPick={!stream}
          onChange={(id, acc) => {
            setAccountId(id);
            setAccount(acc);
          }}
          disabled={busy}
        />
      </Field>

      {stream && activeToggle}

      <MoreOptions>
        <Field label={t('inc.form.type')} asGroup>
          <div className="row" role="radiogroup" aria-label={t('inc.form.type')} data-testid="inc-source">
            {STREAM_SOURCE_TYPES.map((s) => (
              <Button
                key={s}
                role="radio"
                aria-checked={source === s}
                variant="secondary"
                className={styles.choice}
                onClick={() => pickSource(s)}
                disabled={busy}
                data-testid={`inc-source-${s}`}
              >
                {t(`inc.source.${s}`)}
              </Button>
            ))}
          </div>
        </Field>

        <Field label={t('add.category')}>
          <CategoryPicker
            ws={ws}
            kind="income"
            allowNew
            value={effectiveLabelId}
            onChange={(id) => {
              setLabelId(id);
              setLabelTouched(true);
            }}
            disabled={busy}
          />
        </Field>

        {!stream && activeToggle}

        <Field label={t('inc.gross.before')} error={show('gross')}>
          <MoneyInput value={gross} onChange={setGross} currency={currency} disabled={busy} name="gross_amount" />
        </Field>
        <Field label={t('inc.notes')}>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} disabled={busy} rows={2} maxLength={500} />
        </Field>
      </MoreOptions>

      {error && (
        <p className="ui-dialog-error" role="alert">
          {error}
        </p>
      )}

      <div className="row">
        <Button type="submit" variant="primary" loading={busy} data-testid="inc-save">
          {t('inc.save')}
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
