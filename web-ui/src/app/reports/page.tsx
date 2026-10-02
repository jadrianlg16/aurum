'use client';

/**
 * Reports — the monthly review, the net-worth series and the real financial statements.
 *
 * Statements come from `GET /ledger/{ws}/statements/{period}?type=pnl|balance|cashflow`:
 * the API returns sections with per-account rows, a section total and a net,
 * each already an `Amount`, plus its `Explain`. The table below is a rendering of that payload
 * and nothing else — no total is summed in the browser.
 */
import { Fragment, useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section, Sparkline } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { ReportPacksPanel } from '@/components/ReportPacks';
import { useToast } from '@/components/Ui3';
import { getAccountsOverview, getIncome, getReview, getStatement } from '@/lib/api';
import { decimalSign, formatPeriod } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { StatementType } from '@/lib/types';

const STATEMENT_TYPES: StatementType[] = ['pnl', 'balance', 'cashflow'];

export default function ReportsPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();
  const [period, setPeriod] = useState(closePeriod());
  const [stmtType, setStmtType] = useState<StatementType>('pnl');

  const statement = useResource(
    useCallback(() => getStatement(ws, period, stmtType), [ws, period, stmtType]),
    [ws, period, stmtType],
  );
  const review = useResource(useCallback(() => getReview(ws, period), [ws, period]), [ws, period]);
  const accounts = useResource(useCallback(() => getAccountsOverview(ws), [ws]), [ws]);
  const income = useResource(useCallback(() => getIncome(ws), [ws]), [ws]);
  // The bilingual PDF packs live at the top of this screen: they are the
  // deliverable, the sections below are the live figures they are built from.
  const toast = useToast();

  return (
    <>
      <div className="page-head">
        <h1>{t('reports.title')}</h1>
        <div className="spacer" />
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
      </div>

      <div className="stack">
        <ReportPacksPanel ws={ws} toast={toast} />

        <Section title={`${t('reports.review')} · ${formatPeriod(period, lang)}`}>
          {review.loading ? (
            <Loading />
          ) : review.error ? (
            <ErrorBox message={review.error} onRetry={review.reload} />
          ) : !review.data ? (
            <Empty />
          ) : (
            <>
              <div className="grid cols-3">
                <div>
                  <div className="metric-label">{t('home.income')}</div>
                  <div className="metric-value sm">
                    <Money value={review.data.income} compactCents />
                  </div>
                </div>
                <div>
                  <div className="metric-label">{t('home.spend')}</div>
                  <div className="metric-value sm">
                    <Money value={review.data.expense} compactCents />
                  </div>
                </div>
                <div>
                  <div className="metric-label">{t('home.net')}</div>
                  <div className="metric-value sm">
                    <Money value={review.data.net} compactCents sign />
                  </div>
                </div>
              </div>
              <Explain explain={review.data.explain} />

              <h3 style={{ marginTop: 16 }}>{t('reports.top_labels')}</h3>
              <table>
                <thead>
                  <tr>
                    <th>{t('common.label')}</th>
                    <th className="num">{t('common.amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {review.data.top_labels.map((r) => (
                    <tr key={r.label}>
                      <td>{r.label}</td>
                      <td className="num">
                        <Money value={{ amount: r.amount, currency: review.data!.income.currency }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="row small muted" style={{ marginTop: 12 }}>
                <span>
                  {t('reports.delta')} {t('home.income')}:{' '}
                  {decimalSign(review.data.vs_previous_month.income_delta) === 0 ? (
                    '—'
                  ) : (
                    <Money value={{ amount: review.data.vs_previous_month.income_delta, currency: review.data.income.currency }} sign />
                  )}
                </span>
                <span>
                  {t('reports.delta')} {t('home.spend')}:{' '}
                  {decimalSign(review.data.vs_previous_month.expense_delta) === 0 ? (
                    '—'
                  ) : (
                    <Money value={{ amount: review.data.vs_previous_month.expense_delta, currency: review.data.income.currency }} sign />
                  )}
                </span>
              </div>

              {review.data.anomalies.length > 0 && (
                <>
                  <h3 style={{ marginTop: 16 }}>{t('reports.anomalies')}</h3>
                  <div className="stack" style={{ gap: 6 }}>
                    {review.data.anomalies.map((a, i) => (
                      <div key={i} className="row small">
                        <span>{JSON.stringify(a)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </Section>

        <Section
          title={t('stmt.title')}
          actions={
            <div className="tabs" role="tablist" style={{ margin: 0 }}>
              {STATEMENT_TYPES.map((x) => (
                <button
                  key={x}
                  type="button"
                  role="tab"
                  aria-selected={stmtType === x}
                  onClick={() => setStmtType(x)}
                >
                  {t(`stmt.${x}` as 'stmt.pnl')}
                </button>
              ))}
            </div>
          }
        >
          {statement.loading ? (
            <Loading />
          ) : statement.error ? (
            <ErrorBox message={statement.error} onRetry={statement.reload} />
          ) : !statement.data ? (
            <Empty />
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t('common.account')}</th>
                      <th className="num">{t('common.amount')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statement.data.sections.map((sec) => (
                      <Fragment key={sec.title}>
                        <tr>
                          <th colSpan={2} style={{ textAlign: 'left' }}>
                            {sec.title}
                          </th>
                        </tr>
                        {sec.rows.map((r) => (
                          <tr key={`${sec.title}-${r.account}`}>
                            <td className="money small">
                              {r.label}
                              <span className="muted" style={{ marginLeft: 8 }}>
                                {r.account}
                              </span>
                            </td>
                            <td className="num">
                              <Money value={r.amount} sign />
                            </td>
                          </tr>
                        ))}
                        <tr>
                          <td>
                            <strong>{t('stmt.section_total')}</strong>
                          </td>
                          <td className="num">
                            <strong>
                              <Money value={sec.total} sign />
                            </strong>
                          </td>
                        </tr>
                      </Fragment>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td>
                        <strong>{t('stmt.net')}</strong>
                      </td>
                      <td className="num">
                        <strong>
                          <Money value={statement.data.net} sign />
                        </strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              <Explain explain={statement.data.explain} />
            </>
          )}
        </Section>

        <div className="two-pane">
          <Section title={t('reports.networth')}>
            {accounts.loading ? (
              <Loading />
            ) : accounts.error ? (
              <ErrorBox message={accounts.error} onRetry={accounts.reload} />
            ) : (
              <>
                <Sparkline
                  height={110}
                  points={(accounts.data?.net_worth_series ?? []).map((p) => ({
                    label: formatPeriod(p.month, lang),
                    value: { amount: p.net_worth, currency: accounts.data!.net_worth.currency },
                  }))}
                  columns
                />
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>{t('common.period')}</th>
                      <th className="num">{t('home.net_worth')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(accounts.data?.net_worth_series ?? []).slice(-6).map((p) => (
                      <tr key={p.month}>
                        <td>{formatPeriod(p.month, lang)}</td>
                        <td className="num">
                          <Money value={{ amount: p.net_worth, currency: accounts.data!.net_worth.currency }} sign />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </Section>

          <Section title={t('home.income')}>
            {income.data && (
              <>
                <h3 style={{ marginTop: 14 }}>{t('home.income')}</h3>
                <Sparkline
                  points={income.data.months.map((m) => ({ label: formatPeriod(m.month, lang), value: m.gross }))}
                  columns
                />
                <table style={{ marginTop: 10 }}>
                  <thead>
                    <tr>
                      <th>{t('common.description')}</th>
                      <th className="num">{t('common.total')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {income.data.sources.map((s) => {
                      const last = Object.keys(s.months).sort().pop();
                      return (
                        <tr key={s.account}>
                          <td>{s.account}</td>
                          <td className="num">
                            <Money value={last ? { amount: s.months[last], currency: income.data!.smoothed_average.currency } : null} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <Explain explain={income.data.explain} />
              </>
            )}
          </Section>
        </div>
      </div>

      {toast.node}
    </>
  );
}
