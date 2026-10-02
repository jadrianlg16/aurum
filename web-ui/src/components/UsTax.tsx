'use client';

/**
 * Taxes › US — the organizer view for a US (Texas) sole proprietor.
 *
 * Everything on screen is the API's arithmetic: Schedule C lines, SE tax, federal income tax
 * (whose bracket walk lives inside its own Explain), the quarterly estimates with their due
 * dates, and the Texas franchise no-tax-due card from a second endpoint. The banner and the
 * API's own `disclaimer` both stay visible: this screen is an organizer for a preparer, never
 * a return.
 */
import { useCallback } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { UnverifiedList } from '@/components/VerifyChips';
import { getTxFranchise, getUsTax, organizerPdfUrl } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import type { Amount } from '@/lib/types';

function AccountRows({ rows }: { rows: Record<string, Amount> }) {
  const entries = Object.entries(rows);
  if (entries.length === 0) return <Empty />;
  return (
    <div className="table-scroll">
      <table>
        <tbody>
          {entries.map(([account, amount]) => (
            <tr key={account}>
              <td className="small" style={{ fontFamily: 'var(--mono)' }}>
                {account}
              </td>
              <td className="num">
                <Money value={amount} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function UsTaxPanel({ ws, year }: { ws: string; year: number }) {
  const { t, lang } = useI18n();
  const us = useResource(useCallback(() => getUsTax(ws, year), [ws, year]), [ws, year]);
  const tx = useResource(useCallback(() => getTxFranchise(ws, year), [ws, year]), [ws, year]);

  if (us.loading) return <Loading />;
  if (us.error) return <ErrorBox message={us.error} onRetry={us.reload} />;
  if (!us.data) return <Empty />;
  const d = us.data;

  if (!d.applicable) {
    return <div className="banner info">{t('tax.us.not_applicable')}</div>;
  }

  return (
    <div className="stack">
      <div className="banner warn strong">{t('tax.us.banner')}</div>

      <div className="row small muted">
        <span className="badge neutral">{d.profile.filing_status}</span>
        <span className="badge neutral">{d.profile.entity_type}</span>
        <span className="badge neutral">{d.profile.state}</span>
        <div style={{ flex: 1 }} />
        <a className="btn" href={organizerPdfUrl(ws, year)} target="_blank" rel="noreferrer noopener">
          {t('tax.us.organizer')}
        </a>
      </div>

      <div className="grid cols-4">
        <div className="card">
          <div className="metric-label">{t('tax.us.net')}</div>
          <div className="metric-value">
            <Money value={d.schedule_c.net} compactCents />
          </div>
          <Explain explain={d.schedule_c.explain} />
        </div>
        <div className="card">
          <div className="metric-label">{t('tax.us.se_tax')}</div>
          <div className="metric-value">
            <Money value={d.se_tax.value} />
          </div>
          <div className="small muted" style={{ marginTop: 4 }}>
            {t('tax.us.se_deductible')} <Money value={d.se_tax.deductible_half} />
          </div>
          <Explain explain={d.se_tax.explain} />
        </div>
        <div className="card">
          <div className="metric-label">{t('tax.us.income_tax')}</div>
          <div className="metric-value">
            <Money value={d.income_tax.value} />
          </div>
          <div className="small muted" style={{ marginTop: 4 }}>
            {t('tax.us.bracket_walk')}
          </div>
          <Explain explain={d.income_tax.explain} />
        </div>
        <div className="card">
          <div className="metric-label">{t('tax.us.total_tax')}</div>
          <div className="metric-value">
            <Money value={d.total_tax} compactCents />
          </div>
        </div>
      </div>

      {d.warnings.length > 0 && (
        <div className="banner info">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {d.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <Section title={t('tax.us.schedule_c')}>
        <div className="table-scroll">
          <table>
            <tbody>
              <tr>
                <td>{t('tax.us.gross')}</td>
                <td className="num">
                  <Money value={d.schedule_c.gross_receipts} />
                </td>
              </tr>
              <tr>
                <td>{t('tax.us.returns')}</td>
                <td className="num">
                  <Money value={d.schedule_c.returns_and_allowances} />
                </td>
              </tr>
              <tr>
                <td>{t('tax.us.cogs')}</td>
                <td className="num">
                  <Money value={d.schedule_c.cost_of_goods_sold} />
                </td>
              </tr>
              <tr>
                <td>{t('tax.us.expenses')}</td>
                <td className="num">
                  <Money value={d.schedule_c.expenses} />
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{t('tax.us.net')}</strong>
                </td>
                <td className="num">
                  <strong>
                    <Money value={d.schedule_c.net} />
                  </strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>
          {t('tax.us.transactions')}: {d.schedule_c.transactions}
        </p>

        <div className="grid cols-2" style={{ marginTop: 12 }}>
          <div>
            <h3>{t('tax.us.income_accounts')}</h3>
            <AccountRows rows={d.schedule_c.income_by_account} />
          </div>
          <div>
            <h3>{t('tax.us.by_account')}</h3>
            <AccountRows rows={d.schedule_c.expenses_by_account} />
          </div>
        </div>
      </Section>

      <Section title={t('tax.us.quarterly')}>
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="metric-label">{t('tax.us.amount_each')}</span>
          <strong>
            <Money value={d.quarterly.amount_each} />
          </strong>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('tax.us.due_date')}</th>
                <th className="num">{t('common.amount')}</th>
              </tr>
            </thead>
            <tbody>
              {d.quarterly.due_dates.map((dd) => (
                <tr key={dd}>
                  <td>{formatDate(dd, lang)}</td>
                  <td className="num">
                    <Money value={d.quarterly.amount_each} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Explain explain={d.quarterly.explain} />
      </Section>

      <Section title={t('tax.us.franchise')}>
        {tx.loading ? (
          <Loading />
        ) : tx.error ? (
          <ErrorBox message={tx.error} onRetry={tx.reload} />
        ) : !tx.data ? (
          <Empty />
        ) : (
          <>
            <div className="row">
              <span className={`badge ${tx.data.no_tax_due ? 'pos' : 'warn'}`}>
                {tx.data.no_tax_due ? t('tax.us.no_tax_due') : t('tax.us.tax_due')}
              </span>
              <div style={{ flex: 1 }} />
              <strong>
                <Money value={tx.data.tax} />
              </strong>
            </div>
            <div className="grid cols-2" style={{ marginTop: 10 }}>
              <div>
                <div className="metric-label">{t('tax.us.total_revenue')}</div>
                <div className="metric-value sm">
                  <Money value={tx.data.total_revenue} compactCents />
                </div>
              </div>
              <div>
                <div className="metric-label">{t('tax.us.threshold')}</div>
                <div className="metric-value sm">
                  <Money value={tx.data.no_tax_due_threshold} compactCents />
                </div>
              </div>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>
              {t('tax.us.franchise_note')}
            </p>
            <Explain explain={tx.data.explain} />
          </>
        )}
      </Section>

      <UnverifiedList keys={d.unverified_constants} />

      <p className="notice">{d.disclaimer}</p>
    </div>
  );
}
