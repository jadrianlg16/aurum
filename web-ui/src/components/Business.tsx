'use client';

/**
 * Business workspace panels (`aurum/business`): KPIs, the invoicing register,
 * payroll and the MX/NL constant table.
 *
 * Everything on these screens is a figure the API computed, rendered verbatim. The only
 * numbers this file derives are bar widths (see `BarRows`). Two product rules are visible in
 * the markup:
 *  - the tax reserve prints its `warnings` next to the figure with a `(verify)` chip, because
 *    a reserve computed off a non-RESICO regime is an approximation;
 *  - payroll is a **draft**: the run says so, the PDF link says so, and nothing here stamps,
 *    files or sends anything. `POST /invoices/remind` likewise returns text to copy.
 */
import { useCallback, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Metric, Section } from './Bits';
import { Explain } from './Explain';
import { BarRows, CopyButton, verifyFlag, type Toaster } from './Ui3';
import { VerifyChip } from './VerifyChips';
import {
  getBusinessConstants,
  getBusinessKpis,
  getInvoiceRegister,
  getInvoiceReminder,
  listEmployees,
  listPayrollRuns,
  payrollDraftPdfUrl,
  runPayroll,
} from '@/lib/api';
import { formatDate, formatPeriod } from '@/lib/format';
import { useHealth, writeGuard } from '@/lib/health';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import type { InvoiceReminder, PayrollRun, PayrollTotalKey } from '@/lib/types';

/* --------------------------------------------------------------------- KPIs */

export function BusinessKpisPanel({ ws, period }: { ws: string; period: string }) {
  const { t, lang } = useI18n();
  const kpis = useResource(useCallback(() => getBusinessKpis(ws, period), [ws, period]), [ws, period]);

  if (kpis.loading) return <Loading />;
  if (kpis.error) return <ErrorBox message={kpis.error} onRetry={kpis.reload} />;
  if (!kpis.data) return <Empty />;
  const k = kpis.data;

  return (
    <div className="stack">
      <div className="grid cols-3">
        <Metric label={t('biz.revenue')} value={<Money value={k.revenue} compactCents />} explain={k.revenue.explain} />
        <Metric
          label={t('biz.gross_margin')}
          value={k.gross_margin.percent ? `${k.gross_margin.percent}%` : '—'}
          sub={
            <>
              {t('biz.gross_profit')}: <Money value={k.gross_profit} compactCents />
            </>
          }
          explain={k.gross_margin.explain}
        />
        <Metric
          label={t('biz.operating_profit')}
          value={<Money value={k.operating_profit} sign compactCents />}
          sub={
            <>
              {t('biz.cogs')}: <Money value={k.cogs} compactCents />
            </>
          }
          explain={k.operating_profit.explain}
        />
      </div>

      <div className="grid cols-3">
        <Metric label={t('biz.cash')} value={<Money value={k.cash} compactCents />} explain={k.cash.explain} />
        <Metric
          label={t('biz.receivables')}
          value={<Money value={k.receivables} compactCents />}
          explain={k.receivables.explain}
        />
        <Metric
          label={t('biz.payables')}
          value={<Money value={k.payables} compactCents />}
          explain={k.payables.explain}
        />
      </div>

      <div className="two-pane">
        <Section title={t('biz.opex')}>
          <div className="metric-value sm">
            <Money value={k.operating_expenses.total} compactCents />
          </div>
          <div style={{ marginTop: 12 }}>
            <BarRows
              rows={k.operating_expenses.by_group.map((g) => ({ label: g.group, amount: g.amount }))}
            />
          </div>
          <Explain explain={k.operating_expenses.explain} />
        </Section>

        <Section title={t('biz.runway')}>
          <div className="metric-value sm">
            {k.runway.months ? `${k.runway.months} ${t('biz.runway.months')}` : '—'}
          </div>
          <p className="small muted" style={{ marginTop: 6 }}>
            {t('biz.runway.burn')}: <Money value={k.runway.average_burn} compactCents /> ·{' '}
            {k.runway.lookback_months} {t('biz.runway.lookback')}
          </p>
          <Explain explain={k.runway.explain} />
        </Section>
      </div>

      <Section
        title={t('biz.tax_reserve')}
        actions={k.tax_reserve.warnings.some(verifyFlag) ? <VerifyChip /> : null}
      >
        <div className="grid cols-3">
          <div>
            <div className="metric-label">{t('common.total')}</div>
            <div className="metric-value sm">
              <Money value={k.tax_reserve.total} compactCents />
            </div>
          </div>
          <div>
            <div className="metric-label">{t('biz.tax_reserve.isr')}</div>
            <div className="metric-value sm">
              <Money value={k.tax_reserve.isr} compactCents />
            </div>
          </div>
          <div>
            <div className="metric-label">{t('biz.tax_reserve.iva')}</div>
            <div className="metric-value sm">
              <Money value={k.tax_reserve.iva} compactCents />
            </div>
          </div>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          {t('biz.tax_reserve.source')}: <code>{k.tax_reserve.source}</code> · {t('common.period')}:{' '}
          {formatPeriod(k.period, lang)}
        </p>
        {k.tax_reserve.warnings.length > 0 && (
          <ul className="warn-list">
            {k.tax_reserve.warnings.map((w) => (
              <li key={w}>
                {w} {verifyFlag(w) ? <VerifyChip /> : null}
              </li>
            ))}
          </ul>
        )}
        <Explain explain={k.tax_reserve.explain} />
      </Section>
    </div>
  );
}

/* ---------------------------------------------------------------- invoicing */

export function BusinessInvoicesPanel({ ws, toast }: { ws: string; toast: Toaster }) {
  const { t, lang } = useI18n();
  const { demoMode } = useHealth();
  const reg = useResource(useCallback(() => getInvoiceRegister(ws), [ws]), [ws]);
  const [reminder, setReminder] = useState<InvoiceReminder | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const draft = (uuid: string) => {
    setBusy(uuid);
    setErr(null);
    getInvoiceReminder(ws, uuid)
      .then(setReminder)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(null));
  };

  if (reg.loading) return <Loading />;
  if (reg.error) return <ErrorBox message={reg.error} onRetry={reg.reload} />;
  if (!reg.data) return <Empty />;
  const r = reg.data;

  return (
    <div className="stack">
      <div className="grid cols-4">
        <Metric label={t('biz.inv.issued')} value={<Money value={r.issued} compactCents />} sub={`${r.counts.issued} ${t('biz.inv.invoices')}`} />
        <Metric label={t('biz.inv.collected')} value={<Money value={r.collected} compactCents />} />
        <Metric
          label={t('biz.inv.outstanding')}
          value={<Money value={r.outstanding} compactCents />}
          sub={`${r.counts.open} ${t('biz.inv.open')}`}
        />
        <Metric
          label={t('biz.inv.dso')}
          value={r.dso_days ?? '—'}
          sub={`${t('biz.inv.as_of')} ${formatDate(r.as_of, lang)}`}
        />
      </div>

      <Section title={t('biz.inv.aging')}>
        <BarRows
          rows={r.aging.map((b) => ({
            label: b.bucket,
            amount: b.amount,
            note: `${b.invoices} ${t('biz.inv.invoices')}`,
          }))}
        />
        <Explain explain={r.explain} />
      </Section>

      <Section title={t('biz.inv.open')}>
        {r.open_invoices.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('biz.inv.uuid')}</th>
                  <th>{t('common.date')}</th>
                  <th>{t('biz.inv.client')}</th>
                  <th>{t('biz.inv.method')}</th>
                  <th className="num">{t('common.total')}</th>
                  <th className="num">{t('biz.inv.outstanding')}</th>
                  <th className="num">{t('biz.inv.age')}</th>
                  <th>{t('biz.inv.bucket')}</th>
                  <th className="num">{t('biz.inv.reps')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {r.open_invoices.map((inv) => (
                  <tr key={inv.uuid}>
                    <td className="mono small">{inv.uuid}</td>
                    <td>{formatDate(inv.fecha, lang)}</td>
                    <td className="mono small">{inv.client_rfc}</td>
                    <td>{inv.metodo_pago}</td>
                    <td className="num">
                      <Money value={inv.total} />
                    </td>
                    <td className="num">
                      <Money value={inv.outstanding} />
                    </td>
                    <td className="num">{inv.age_days}</td>
                    <td>{inv.bucket}</td>
                    <td className="num">{inv.reps}</td>
                    <td className="num">
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => draft(inv.uuid)}
                        disabled={busy === inv.uuid}
                        {...writeGuard(demoMode, t('settings.demo.tooltip'))}
                      >
                        {t('biz.inv.reminder.get')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {err && <p className="err">{err}</p>}
      </Section>

      {reminder && (
        <Section
          title={`${t('biz.inv.reminder')} · ${reminder.client_rfc}`}
          actions={
            <CopyButton
              text={reminder.text[lang] ?? reminder.text.es}
              onDone={(ok) => toast.show(ok ? t('common.copied') : t('common.error'))}
            />
          }
        >
          <label className="field">
            <span className="visually-hidden">{t('biz.inv.reminder')}</span>
            <textarea readOnly rows={8} value={reminder.text[lang] ?? reminder.text.es} />
          </label>
          <p className="small muted">{t('biz.inv.reminder.note')}</p>
        </Section>
      )}

      <Section title={t('biz.inv.top_clients')}>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('biz.inv.client')}</th>
                <th className="num">{t('biz.inv.invoices')}</th>
                <th className="num">{t('biz.inv.issued')}</th>
                <th className="num">{t('biz.inv.paid')}</th>
                <th className="num">{t('biz.inv.outstanding')}</th>
              </tr>
            </thead>
            <tbody>
              {r.top_clients.map((c) => (
                <tr key={c.client_rfc}>
                  <td className="mono small">{c.client_rfc}</td>
                  <td className="num">{c.invoices}</td>
                  <td className="num">
                    <Money value={c.issued} />
                  </td>
                  <td className="num">
                    <Money value={c.paid} />
                  </td>
                  <td className="num">
                    <Money value={c.outstanding} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

/* ------------------------------------------------------------------ payroll */

const TOTAL_KEYS: { key: PayrollTotalKey; label: MsgKey }[] = [
  { key: 'gross', label: 'biz.pay.gross' },
  { key: 'isr_retenido', label: 'biz.pay.isr' },
  { key: 'imss_employee', label: 'biz.pay.imss_employee' },
  { key: 'net', label: 'biz.pay.net' },
  { key: 'imss_employer', label: 'biz.pay.imss_employer' },
  { key: 'infonavit', label: 'biz.pay.infonavit' },
  { key: 'isn', label: 'biz.pay.isn' },
  { key: 'employer_cost', label: 'biz.pay.employer_cost' },
];

export function BusinessPayrollPanel({ ws, period }: { ws: string; period: string }) {
  const { t, lang } = useI18n();
  const { demoMode } = useHealth();
  const employees = useResource(useCallback(() => listEmployees(ws), [ws]), [ws]);
  const runs = useResource(useCallback(() => listPayrollRuns(ws), [ws]), [ws]);
  const [runPeriod, setRunPeriod] = useState(period);
  const [days, setDays] = useState('');
  const [post, setPost] = useState(true);
  const [result, setResult] = useState<PayrollRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    runPayroll(ws, { period: runPeriod, days: days || undefined, post, lang })
      .then((r) => {
        setResult(r);
        runs.reload();
      })
      .catch((ex: unknown) => setErr(ex instanceof Error ? ex.message : String(ex)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="stack">
      <Section title={t('biz.pay.employees')}>
        {employees.loading ? (
          <Loading />
        ) : employees.error ? (
          <ErrorBox message={employees.error} onRetry={employees.reload} />
        ) : !employees.data || employees.data.length === 0 ? (
          <Empty />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('biz.pay.employee')}</th>
                  <th>RFC</th>
                  <th className="num">{t('biz.pay.daily')}</th>
                  <th className="num">{t('biz.pay.sbc')}</th>
                  <th>{t('biz.pay.state')}</th>
                  <th>{t('biz.pay.hired')}</th>
                </tr>
              </thead>
              <tbody>
                {employees.data.map((e) => (
                  <tr key={e.id}>
                    <td>{e.name}</td>
                    <td className="mono small">{e.rfc ?? '—'}</td>
                    <td className="num">
                      <Money value={e.daily_salary} />
                    </td>
                    <td className="num">
                      <Money value={e.sbc_daily} />
                    </td>
                    <td>{e.state}</td>
                    <td>{e.hired_on ? formatDate(e.hired_on, lang) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title={t('biz.pay.run')}>
        <form className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }} onSubmit={submit}>
          <label className="field">
            {t('common.period')}
            <select value={runPeriod} onChange={(e) => setRunPeriod(e.target.value)}>
              {periodsEndingAt(closePeriod(), 12).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t('common.days')}
            <input
              inputMode="decimal"
              value={days}
              placeholder="auto"
              onChange={(e) => setDays(e.target.value.replace(/[^0-9.]/g, ''))}
            />
          </label>
          <label className="row small" style={{ gap: 6 }}>
            <input type="checkbox" checked={post} onChange={(e) => setPost(e.target.checked)} />
            {t('biz.pay.post')}
          </label>
          <button
            type="submit"
            className="btn primary"
            disabled={busy}
            {...writeGuard(demoMode, t('settings.demo.tooltip'))}
          >
            {t('biz.pay.run')}
          </button>
          <span className="badge warn">{t('biz.pay.draft')}</span>
        </form>
        {err && <p className="err">{err}</p>}
      </Section>

      {result && <PayrollRunView run={result} ws={ws} />}

      <Section title={t('biz.pay.runs')} actions={<button type="button" className="btn ghost" onClick={runs.reload}>{t('common.refresh')}</button>}>
        {runs.loading ? (
          <Loading />
        ) : runs.error ? (
          <ErrorBox message={runs.error} onRetry={runs.reload} />
        ) : !runs.data || runs.data.length === 0 ? (
          <Empty text={t('biz.pay.no_runs')} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('common.period')}</th>
                  <th className="num">{t('common.days')}</th>
                  <th className="num">{t('biz.pay.gross')}</th>
                  <th className="num">{t('biz.pay.net')}</th>
                  <th className="num">{t('biz.pay.isr')}</th>
                  <th className="num">{t('biz.pay.imss_employer')}</th>
                  <th className="num">{t('biz.pay.isn')}</th>
                  <th className="num">{t('biz.pay.employer_cost')}</th>
                  <th>{t('biz.pay.txn')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <td>{r.period}</td>
                    <td className="num">{r.days}</td>
                    <td className="num">
                      <Money value={{ amount: r.gross, currency: r.currency }} />
                    </td>
                    <td className="num">
                      <Money value={{ amount: r.net, currency: r.currency }} />
                    </td>
                    <td className="num">
                      <Money value={{ amount: r.isr_retenido, currency: r.currency }} />
                    </td>
                    <td className="num">
                      <Money value={{ amount: r.imss_employer, currency: r.currency }} />
                    </td>
                    <td className="num">
                      <Money value={{ amount: r.isn, currency: r.currency }} />
                    </td>
                    <td className="num">
                      <Money value={{ amount: r.employer_cost, currency: r.currency }} />
                    </td>
                    <td className="mono small">{r.txn_id ?? '—'}</td>
                    <td className="num">
                      <a className="btn ghost" href={payrollDraftPdfUrl(ws, r.id)} target="_blank" rel="noreferrer noopener">
                        {t('biz.pay.pdf')}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

function PayrollRunView({ run, ws }: { run: PayrollRun; ws: string }) {
  const { t } = useI18n();
  return (
    <Section
      title={`${t('biz.pay.totals')} · ${run.period}`}
      actions={
        <div className="row" style={{ gap: 6 }}>
          <span className="badge warn">{t('packs.draft')}</span>
          <a className="btn" href={payrollDraftPdfUrl(ws, run.id)} target="_blank" rel="noreferrer noopener">
            {t('biz.pay.pdf')}
          </a>
        </div>
      }
    >
      <div className="grid cols-4">
        {TOTAL_KEYS.map((k) => (
          <div key={k.key}>
            <div className="metric-label">{t(k.label)}</div>
            <div className="metric-value sm">
              <Money value={run.totals[k.key]} compactCents />
            </div>
          </div>
        ))}
      </div>

      {run.warnings.length > 0 && (
        <ul className="warn-list">
          {run.warnings.map((w) => (
            <li key={w}>
              {w} {verifyFlag(w) ? <VerifyChip /> : null}
            </li>
          ))}
        </ul>
      )}

      <Explain explain={run.explain} />

      <h3 style={{ marginTop: 16 }}>{t('biz.pay.lines')}</h3>
      <div className="stack" style={{ gap: 10 }}>
        {run.lines.map((line) => (
          <details key={line.employee_id} className="line-detail">
            <summary>
              <span>{line.name}</span>
              <span className="muted small">
                {t('biz.pay.gross')} <Money value={line.gross} /> · {t('biz.pay.net')}{' '}
                <Money value={line.net} />
              </span>
              {line.sbc_capped && <span className="badge info">{t('biz.pay.capped')}</span>}
            </summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('common.key')}</th>
                    <th className="num">{t('common.value')}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{t('biz.pay.isr')}</td>
                    <td className="num">
                      <Money value={line.isr_retenido} />
                    </td>
                  </tr>
                  <tr>
                    <td>{t('biz.pay.subsidy')}</td>
                    <td className="num">
                      <Money value={line.subsidio_empleo} />
                    </td>
                  </tr>
                  <tr>
                    <td>{t('biz.pay.imss_employee')}</td>
                    <td className="num">
                      <Money value={line.imss_employee} />
                    </td>
                  </tr>
                  <tr>
                    <td>{t('biz.pay.imss_employer')}</td>
                    <td className="num">
                      <Money value={line.imss_employer} />
                    </td>
                  </tr>
                  <tr>
                    <td>{t('biz.pay.infonavit')}</td>
                    <td className="num">
                      <Money value={line.infonavit} />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h4>{t('biz.pay.branches')}</h4>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('common.key')}</th>
                    <th className="num">{t('common.amount')}</th>
                    <th>{t('explain.formula')}</th>
                  </tr>
                </thead>
                <tbody>
                  {line.imss_employer_branches.map((b) => (
                    <tr key={b.branch}>
                      <td>{b.branch}</td>
                      <td className="num">
                        <Money value={b.amount} />
                      </td>
                      <td className="formula">
                        {b.formula} {verifyFlag(b.formula) ? <VerifyChip /> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Explain explain={line.explain} />
          </details>
        ))}
      </div>
    </Section>
  );
}

/* ---------------------------------------------------------------- constants */

export function BusinessConstantsPanel() {
  const { t, lang } = useI18n();
  const consts = useResource(useCallback(() => getBusinessConstants(), []), []);
  const [onlyUnverified, setOnlyUnverified] = useState(false);

  const rows = useMemo(() => {
    const all = consts.data?.constants ?? [];
    return onlyUnverified ? all.filter((c) => !c.verified) : all;
  }, [consts.data, onlyUnverified]);

  if (consts.loading) return <Loading />;
  if (consts.error) return <ErrorBox message={consts.error} onRetry={consts.reload} />;
  if (!consts.data) return <Empty />;

  return (
    <Section
      title={t('biz.const.title')}
      actions={
        <label className="row small" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={onlyUnverified}
            onChange={(e) => setOnlyUnverified(e.target.checked)}
          />
          {t('biz.const.unverified')}
        </label>
      }
    >
      <p className="small muted">
        {t('biz.const.year')}: {consts.data.year} · {t('biz.const.verified_on')}:{' '}
        {formatDate(consts.data.verified_on, lang)}
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('common.key')}</th>
              <th className="num">{t('common.value')}</th>
              <th>{t('biz.const.verified')}</th>
              <th>{t('explain.citations')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.key}>
                <td className="mono small">{c.key}</td>
                <td className="num money">{c.value}</td>
                <td>{c.verified ? <span className="badge pos">✓</span> : <VerifyChip />}</td>
                <td className="small">
                  {c.citation.law} {c.citation.article}
                  {c.source_url && (
                    <>
                      {' · '}
                      <a href={c.source_url} target="_blank" rel="noreferrer noopener">
                        {t('common.source')}
                      </a>
                    </>
                  )}
                  {c.note && <div className="muted">{c.note}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {consts.data.unverified.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="metric-label">{t('biz.const.unverified')}</div>
          <div className="row small" style={{ flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {consts.data.unverified.map((k) => (
              <VerifyChip key={k} label={k} />
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}
