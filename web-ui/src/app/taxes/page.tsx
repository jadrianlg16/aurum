'use client';

/**
 * Taxes › Month close — the prefill audit.
 *
 * Aurum's figures next to the SAT prefill Aurum predicts, every difference listed with its
 * kind badge and its own Explain, the deadline, the DRAFT PDF, and a banner that never lets
 * the screen be mistaken for a filing tool.
 */
import { useCallback, useEffect, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { UsTaxPanel } from '@/components/UsTax';
import { draftPdfUrl, getMonthClose } from '@/lib/api';
import { daysUntil, formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { queryTab } from '@/lib/query';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { Amount, DiffKind } from '@/lib/types';

type Tab = 'mx' | 'us';

const DIFF_KEY: Record<DiffKind, MsgKey> = {
  pue_not_collected: 'diff.pue_not_collected',
  ppd_missing_rep: 'diff.ppd_missing_rep',
  deposit_without_cfdi: 'diff.deposit_without_cfdi',
  cash_paid_expense: 'diff.cash_paid_expense',
  fixed_asset_iva: 'diff.fixed_asset_iva',
};

const DIFF_TONE: Record<DiffKind, string> = {
  pue_not_collected: 'neg',
  ppd_missing_rep: 'warn',
  deposit_without_cfdi: 'neg',
  cash_paid_expense: 'warn',
  fixed_asset_iva: 'info',
};

/** One row of the Aurum-vs-prefill comparison. No subtraction here: both sides come from the API. */
function CompareRow({ label, aurum, prefill }: { label: string; aurum: Amount; prefill: Amount }) {
  const differs = aurum.amount !== prefill.amount;
  return (
    <tr>
      <td>{label}</td>
      <td className="num">
        <Money value={aurum} />
      </td>
      <td className="num">
        <Money value={prefill} />
      </td>
      <td>{differs ? <span className="badge warn">≠</span> : <span className="badge pos">=</span>}</td>
    </tr>
  );
}

/** The years offered by the US picker: this year and the four before it. */
function recentYears(): number[] {
  const now = new Date().getUTCFullYear();
  return [0, 1, 2, 3, 4].map((n) => now - n);
}

export default function TaxesPage() {
  const { t, lang } = useI18n();
  const { ws, current } = useWorkspace();
  const [period, setPeriod] = useState(closePeriod());
  const [year, setYear] = useState(() => recentYears()[0]);

  // Which tabs exist is the workspace's own `jurisdictions`: a MX-only book never sees the
  // US organizer, and a US-only book opens straight on it.
  const jurisdictions = current?.jurisdictions ?? ['MX'];
  const hasUs = jurisdictions.includes('US');
  const hasMx = jurisdictions.includes('MX');
  // Starts at the literal default so the server-rendered markup and the client's first render
  // agree (no `window` at prerender time); the effect below then applies `?tab=` — and the
  // workspace's own jurisdictions — as an ordinary post-mount update. See `useQueryTab` in
  // `lib/query.ts` for why reading `?tab=` straight in the initializer corrupts hydration.
  const [tab, setTab] = useState<Tab>('mx');
  useEffect(() => {
    // A  deep link wins as soon as the workspace is known to have US; otherwise the
    // tab follows the workspace's own jurisdictions.
    // A `?tab=us` deep link wins as soon as the workspace is known to include US; otherwise
    // the open tab follows the workspace's own jurisdictions.
    const wanted = queryTab(['mx', 'us'] as const);
    setTab(wanted === 'us' && hasUs ? 'us' : hasMx ? 'mx' : 'us');
  }, [hasMx, hasUs, ws]);

  const close = useResource(
    useCallback(
      () => (tab === 'mx' ? getMonthClose(ws, period) : Promise.resolve(null)),
      [ws, period, tab],
    ),
    [ws, period, tab],
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{tab === 'us' ? t('tax.us.title') : t('tax.title')}</h1>
          <div className="sub">{ws}</div>
        </div>
        <div className="spacer" />
        {tab === 'us' ? (
          <label className="field">
            {t('common.year')}
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {recentYears().map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label className="field">
              {t('common.period')}
              <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                {periodsEndingAt(closePeriod(), 12).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <a className="btn" href={draftPdfUrl(ws, period)} target="_blank" rel="noreferrer noopener">
              {t('tax.draft_pdf')}
            </a>
          </>
        )}
      </div>

      {hasUs && hasMx && (
        <div className="tabs" role="tablist">
          {(['mx', 'us'] as Tab[]).map((x) => (
            <button key={x} type="button" role="tab" aria-selected={tab === x} onClick={() => setTab(x)}>
              {t(x === 'mx' ? 'tax.tab.mx' : 'tax.tab.us')}
            </button>
          ))}
        </div>
      )}

      {tab === 'us' && <UsTaxPanel ws={ws} year={year} />}

      {tab === 'mx' && (
      <div className="banner warn strong" style={{ marginBottom: 16 }}>
        {t('tax.banner')}
      </div>
      )}

      {tab === 'mx' && (close.loading ? (
        <Loading />
      ) : close.error ? (
        <ErrorBox message={close.error} onRetry={close.reload} />
      ) : !close.data ? (
        <Empty />
      ) : (
        <div className="stack">
          <div className="grid cols-4">
            <div className="card">
              <div className="metric-label">{t('tax.income_collected')}</div>
              <div className="metric-value">
                <Money value={close.data.income.collected} compactCents />
              </div>
              <Explain explain={close.data.income.explain} />
            </div>
            <div className="card">
              <div className="metric-label">{t('tax.isr')}</div>
              <div className="metric-value">
                <Money value={close.data.isr.value} />
              </div>
              <Explain explain={close.data.isr.explain} />
            </div>
            <div className="card">
              <div className="metric-label">{t('tax.iva.payable')}</div>
              <div className="metric-value">
                <Money value={close.data.iva.payable} />
              </div>
              <div className="row small muted" style={{ marginTop: 6 }}>
                <span>
                  {t('tax.iva.trasladado')} <Money value={close.data.iva.trasladado} />
                </span>
                <span>
                  {t('tax.iva.acreditable')} <Money value={close.data.iva.acreditable} />
                </span>
              </div>
              <Explain explain={close.data.iva.explain} />
            </div>
            <div className="card">
              <div className="metric-label">{t('tax.deadline')}</div>
              <div className="metric-value sm">{formatDate(close.data.deadline, lang)}</div>
              <div style={{ marginTop: 6 }}>
                {(() => {
                  const d = daysUntil(close.data.deadline);
                  const tone = d < 0 ? 'neg' : d <= 7 ? 'warn' : 'neutral';
                  return (
                    <span className={`badge ${tone}`}>
                      {d < 0 ? t('home.overdue') : d === 0 ? t('home.today') : `${d} ${t('home.days')}`}
                    </span>
                  );
                })()}
                <span className="badge neutral" style={{ marginLeft: 6 }}>
                  {t('tax.status')}: {close.data.status}
                </span>
              </div>
              <div className="row small muted" style={{ marginTop: 8 }}>
                <span>
                  {t('tax.retentions.isr')} <Money value={close.data.retentions.isr} />
                </span>
                <span>
                  {t('tax.retentions.iva')} <Money value={close.data.retentions.iva} />
                </span>
              </div>
            </div>
          </div>

          {close.data.warnings.length > 0 && (
            <div className="banner info">
              <strong>{t('tax.warnings')}</strong>
              <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                {close.data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <Section title={`${t('tax.aurum')} · ${t('tax.prefill')}`}>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th />
                    <th className="num">{t('tax.aurum')}</th>
                    <th className="num">{t('tax.prefill')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  <CompareRow
                    label={t('tax.income_collected')}
                    aurum={close.data.income.collected}
                    prefill={close.data.prefill_expected.income}
                  />
                  <CompareRow label={t('tax.isr')} aurum={close.data.isr.value} prefill={close.data.prefill_expected.isr} />
                  <CompareRow
                    label={t('tax.iva.acreditable')}
                    aurum={close.data.iva.acreditable}
                    prefill={close.data.prefill_expected.iva_acreditable}
                  />
                </tbody>
              </table>
            </div>

            <Explain explain={close.data.prefill_expected.explain} />

            {close.data.income.by_rule.length > 0 && (
              <>
                <h3 style={{ marginTop: 16 }}>{t('tax.by_rule')}</h3>
                <table>
                  <tbody>
                    {close.data.income.by_rule.map((r, i) => (
                      <tr key={i}>
                        <td className="small">{r.rule}</td>
                        <td className="num">
                          <Money value={r.value} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </Section>

          <Section title={`${t('tax.diffs')} · ${close.data.diffs.length}`}>
            {close.data.diffs.length === 0 ? (
              <Empty text={t('tax.diffs.none')} />
            ) : (
              <div className="stack" style={{ gap: 12 }}>
                {close.data.diffs.map((d, i) => (
                  <div key={`${d.kind}-${i}`} className="card">
                    <div className="row">
                      <span className={`badge ${DIFF_TONE[d.kind]}`}>{t(DIFF_KEY[d.kind])}</span>
                      <div style={{ flex: 1 }} />
                      <strong>
                        <Money value={d.amount} />
                      </strong>
                    </div>
                    {d.documents.length > 0 && (
                      <div className="row small muted" style={{ marginTop: 6 }}>
                        <span>{t('tax.documents')}:</span>
                        {d.documents.map((u) => (
                          <span key={u} className="rule-chip">
                            {u.slice(0, 13)}…
                          </span>
                        ))}
                      </div>
                    )}
                    <Explain explain={d.explain} />
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      ))}
    </>
  );
}
