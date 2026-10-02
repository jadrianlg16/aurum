'use client';

/**
 * Cross-border profile wizard → `PUT /api/crossborder/{ws}/profile`.
 *
 * Five steps, because the facts come from five different places in a person's life: where they
 * physically were, where the money came from, what they hold abroad, what passports they carry,
 * and how they would answer the treaty's own tie-breaker questions.
 *
 * Days are integers (a count, so `number` is honest); every money figure stays a decimal
 * *string* from the keystroke to the request body — no `parseFloat` anywhere in this file.
 */
import { useState } from 'react';
import { CheckField, DecimalField, SelectField, TextField } from '@/components/Form';
import { errorMessage, putCrossborderProfile } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import type { CrossborderProfile, XbForeignAccount, XbIncomeSource } from '@/lib/types';

const STEPS = ['days', 'income', 'accounts', 'status', 'treaty'] as const;
type Step = (typeof STEPS)[number];

const STEP_KEY = {
  days: 'xb.step.days',
  income: 'xb.step.income',
  accounts: 'xb.step.accounts',
  status: 'xb.step.status',
  treaty: 'xb.step.treaty',
} as const;

const FILING_STATUSES = ['single', 'married_joint', 'married_separate', 'head_of_household'];
const COUNTRIES = ['MX', 'US', 'other'];
const INCOME_KINDS = ['self_employment', 'wages', 'interest', 'dividends', 'rental', 'capital_gains'];

/** A count field: an integer the user types, kept as a number because it is never money. */
function CountField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="field" style={{ display: 'block', marginBottom: 12 }}>
      <span>{label}</span>
      <input
        type="number"
        min={0}
        max={366}
        value={value}
        onChange={(e) => onChange(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
        style={{ width: '100%', fontFamily: 'var(--mono)' }}
      />
    </label>
  );
}

/** `null` in the API means "unanswered", which is a real answer for the treaty ladder. */
function CountryChoice({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (v: string | null) => void;
}) {
  const { t } = useI18n();
  return (
    <SelectField
      label={label}
      value={value ?? ''}
      onChange={(v) => onChange(v === '' ? null : v)}
      options={[
        { value: '', label: t('xb.unanswered') },
        { value: 'MX', label: 'MX' },
        { value: 'US', label: 'US' },
      ]}
    />
  );
}

export function XbProfileWizard({
  ws,
  initial,
  onSaved,
  onCancel,
}: {
  ws: string;
  initial: CrossborderProfile;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [step, setStep] = useState<Step>('days');
  const [p, setP] = useState<CrossborderProfile>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = (v: Partial<CrossborderProfile>) => setP((prev) => ({ ...prev, ...v }));

  const patchIncome = (i: number, v: Partial<XbIncomeSource>) =>
    setP((prev) => ({
      ...prev,
      income_sources: prev.income_sources.map((r, n) => (n === i ? { ...r, ...v } : r)),
    }));
  const patchAccount = (i: number, v: Partial<XbForeignAccount>) =>
    setP((prev) => ({
      ...prev,
      foreign_accounts: prev.foreign_accounts.map((r, n) => (n === i ? { ...r, ...v } : r)),
    }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await putCrossborderProfile(ws, p);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const idx = STEPS.indexOf(step);

  return (
    <section className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>{t('xb.profile')}</h2>
        <div style={{ flex: 1 }} />
        <button type="button" className="btn ghost" onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>

      <div className="tabs" role="tablist">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={step === s}
            onClick={() => setStep(s)}
          >
            {i + 1}. {t(STEP_KEY[s])}
          </button>
        ))}
      </div>

      {step === 'days' && (
        <div className="grid cols-2">
          <div>
            <CountField label={t('xb.days_mx')} value={p.days_mx} onChange={(v) => patch({ days_mx: v })} />
            <CountField label={t('xb.days_us')} value={p.days_us} onChange={(v) => patch({ days_us: v })} />
            <CountField
              label={t('xb.days_us_prior_1')}
              value={p.days_us_prior_1}
              onChange={(v) => patch({ days_us_prior_1: v })}
            />
            <CountField
              label={t('xb.days_us_prior_2')}
              value={p.days_us_prior_2}
              onChange={(v) => patch({ days_us_prior_2: v })}
            />
          </div>
          <div>
            <CountField
              label={t('xb.days_abroad')}
              value={p.days_abroad_for_feie}
              onChange={(v) => patch({ days_abroad_for_feie: v })}
            />
            <CheckField
              label={t('xb.home_mx')}
              checked={p.home_mx}
              onChange={(v) => patch({ home_mx: v })}
            />
            <CheckField
              label={t('xb.home_us')}
              checked={p.home_us}
              onChange={(v) => patch({ home_us: v })}
            />
            <CheckField
              label={t('xb.bona_fide')}
              checked={p.bona_fide_resident_abroad}
              onChange={(v) => patch({ bona_fide_resident_abroad: v })}
            />
            <CheckField
              label={t('xb.green_card')}
              checked={p.green_card}
              onChange={(v) => patch({ green_card: v })}
            />
          </div>
        </div>
      )}

      {step === 'income' && (
        <div className="stack" style={{ gap: 10 }}>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('common.country')}</th>
                  <th>{t('common.kind')}</th>
                  <th className="num">{t('common.amount')}</th>
                  <th>{t('common.currency')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {p.income_sources.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <select value={r.country} onChange={(e) => patchIncome(i, { country: e.target.value })}>
                        {COUNTRIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select value={r.kind} onChange={(e) => patchIncome(i, { kind: e.target.value })}>
                        {INCOME_KINDS.map((k) => (
                          <option key={k} value={k}>
                            {k}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="num">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={r.amount}
                        onChange={(e) => patchIncome(i, { amount: e.target.value.replace(/[^\d.]/g, '') })}
                        style={{ fontFamily: 'var(--mono)', width: 130 }}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={r.currency}
                        onChange={(e) => patchIncome(i, { currency: e.target.value.toUpperCase() })}
                        style={{ width: 70 }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() =>
                          patch({ income_sources: p.income_sources.filter((_, n) => n !== i) })
                        }
                      >
                        {t('common.remove')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              patch({
                income_sources: [
                  ...p.income_sources,
                  { country: 'US', kind: 'self_employment', amount: '0', currency: 'USD' },
                ],
              })
            }
          >
            + {t('common.add')}
          </button>
        </div>
      )}

      {step === 'accounts' && (
        <div className="stack" style={{ gap: 10 }}>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('common.country')}</th>
                  <th>{t('xb.institution')}</th>
                  <th className="num">{t('xb.max_balance')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {p.foreign_accounts.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <select value={r.country} onChange={(e) => patchAccount(i, { country: e.target.value })}>
                        {COUNTRIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={r.institution ?? ''}
                        onChange={(e) => patchAccount(i, { institution: e.target.value || null })}
                        style={{ width: 220 }}
                      />
                    </td>
                    <td className="num">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={r.max_balance_usd}
                        onChange={(e) =>
                          patchAccount(i, { max_balance_usd: e.target.value.replace(/[^\d.]/g, '') })
                        }
                        style={{ fontFamily: 'var(--mono)', width: 130 }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() =>
                          patch({ foreign_accounts: p.foreign_accounts.filter((_, n) => n !== i) })
                        }
                      >
                        {t('common.remove')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              patch({
                foreign_accounts: [
                  ...p.foreign_accounts,
                  { country: 'MX', institution: null, max_balance_usd: '0' },
                ],
              })
            }
          >
            + {t('common.add')}
          </button>
        </div>
      )}

      {step === 'status' && (
        <div className="grid cols-2">
          <div>
            <TextField
              label={t('xb.citizenship')}
              hint={t('xb.citizenship_hint')}
              value={p.citizenship.join(', ')}
              onChange={(v) =>
                patch({ citizenship: v.split(',').map((x) => x.trim().toUpperCase()).filter(Boolean) })
              }
            />
            <SelectField
              label={t('xb.filing_status')}
              value={p.filing_status}
              onChange={(v) => patch({ filing_status: v })}
              options={FILING_STATUSES.map((f) => ({ value: f, label: f }))}
            />
          </div>
          <div>
            <CountryChoice
              label={t('xb.main_center')}
              value={p.main_professional_center}
              onChange={(v) => patch({ main_professional_center: v })}
            />
            <DecimalField
              label={t('xb.mx_share')}
              value={p.mx_source_income_share ?? ''}
              onChange={(v) => patch({ mx_source_income_share: v || null })}
              placeholder="0.20"
            />
            <DecimalField
              label={t('xb.foreign_tax_paid')}
              value={p.foreign_tax_paid_usd ?? ''}
              onChange={(v) => patch({ foreign_tax_paid_usd: v || '0' })}
            />
          </div>
        </div>
      )}

      {step === 'treaty' && (
        <div className="grid cols-2">
          <div>
            <CountryChoice
              label={t('xb.permanent_home')}
              value={p.treaty_permanent_home}
              onChange={(v) => patch({ treaty_permanent_home: v })}
            />
            <CountryChoice
              label={t('xb.center_vital')}
              value={p.treaty_center_of_vital_interests}
              onChange={(v) => patch({ treaty_center_of_vital_interests: v })}
            />
          </div>
          <div>
            <CountryChoice
              label={t('xb.habitual_abode')}
              value={p.treaty_habitual_abode}
              onChange={(v) => patch({ treaty_habitual_abode: v })}
            />
            <CountryChoice
              label={t('xb.nationality')}
              value={p.treaty_nationality}
              onChange={(v) => patch({ treaty_nationality: v })}
            />
          </div>
        </div>
      )}

      {error && <p className="err">{error}</p>}

      <div className="row" style={{ marginTop: 12 }}>
        <button
          type="button"
          className="btn ghost"
          disabled={idx === 0}
          onClick={() => setStep(STEPS[Math.max(0, idx - 1)])}
        >
          {t('common.back')}
        </button>
        <div style={{ flex: 1 }} />
        {idx < STEPS.length - 1 && (
          <button type="button" className="btn" onClick={() => setStep(STEPS[idx + 1])}>
            {t(STEP_KEY[STEPS[idx + 1]])} →
          </button>
        )}
        <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
          {t('common.save')}
        </button>
      </div>
    </section>
  );
}
