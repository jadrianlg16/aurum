'use client';

/**
 * Plan › Credit — the Buró de Crédito report import (`aurum/creditreport`).
 *
 * The parser is a heuristic, so its `warnings` are shown as prominently as its results: a
 * report that could not be read produces an honest empty table plus the reason, never an
 * invented figure. The "what moves a score" block is education with citations, and the page
 * says out loud that nothing here is a credit decision.
 */
import { useCallback, useRef, useState } from 'react';
import { Empty, ErrorBox, Loading, Section, Sparkline } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { errorMessage, getCreditReport, getCreditReportExplain, importCreditReport } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';

export function CreditReportPanel({ ws }: { ws: string }) {
  const { t, lang } = useI18n();
  const state = useResource(useCallback(() => getCreditReport(ws), [ws]), [ws]);
  const explainer = useResource(useCallback(() => getCreditReportExplain(ws), [ws]), [ws]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      await importCreditReport(ws, file);
      state.reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const latest = state.data?.latest ?? null;
  // Score history is every import that carried a score, oldest first.
  const history = (state.data?.imports ?? [])
    .filter((i) => i.score)
    .slice()
    .reverse();

  return (
    <div className="stack">
      <Section
        title={t('cr.title')}
        actions={
          <div className="row" style={{ gap: 6 }}>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f);
              }}
            />
          </div>
        }
      >
        <p className="small muted">{t('cr.not_a_decision')}</p>
        {busy && <p className="small">{t('cr.importing')}</p>}
        {error && <p className="err">{error}</p>}

        {state.loading ? (
          <Loading />
        ) : state.error ? (
          <ErrorBox message={state.error} onRetry={state.reload} />
        ) : !latest ? (
          <Empty text={t('cr.none')} />
        ) : (
          <>
            <div className="row small muted" style={{ marginTop: 8 }}>
              <span>
                {t('cr.filename')}: <span style={{ fontFamily: 'var(--mono)' }}>{latest.filename}</span>
              </span>
              <span>
                {t('cr.imported_at')}: {formatDate(latest.imported_at.slice(0, 10), lang)}
              </span>
              {latest.score && (
                <span className="badge gold">
                  {t('cr.score')} {String(latest.score.value)}
                  {latest.score.bureau ? ` · ${latest.score.bureau}` : ''}
                </span>
              )}
            </div>

            {latest.warnings.length > 0 && (
              <div className="banner warn" style={{ marginTop: 10 }}>
                <strong>{t('cr.warnings')}</strong>
                <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                  {latest.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            <h3 style={{ marginTop: 14 }}>{t('cr.accounts')}</h3>
            {latest.accounts.length === 0 ? (
              <Empty />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t('cr.grantor')}</th>
                      <th>{t('common.kind')}</th>
                      <th className="num">{t('cr.limit')}</th>
                      <th className="num">{t('cr.balance')}</th>
                      <th>{t('common.status')}</th>
                      <th>{t('cr.opened')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.accounts.map((a, i) => (
                      <tr key={i}>
                        <td>{a.grantor ?? '—'}</td>
                        <td className="small">{a.type ?? '—'}</td>
                        <td className="num money">{a.limit ?? '—'}</td>
                        <td className="num money">{a.balance ?? '—'}</td>
                        <td>{a.status && <span className="badge neutral">{a.status}</span>}</td>
                        <td className="small">{a.opened ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>

      {history.length > 0 && (
        <Section title={t('cr.history')}>
          <Sparkline
            points={history.map((i) => ({
              label: i.imported_at.slice(0, 10),
              value: { amount: String(i.score?.value ?? '0'), currency: '' },
            }))}
            columns
          />
          <div className="table-scroll" style={{ marginTop: 8 }}>
            <table>
              <tbody>
                {history
                  .slice()
                  .reverse()
                  .map((i) => (
                    <tr key={i.id}>
                      <td>{formatDate(i.imported_at.slice(0, 10), lang)}</td>
                      <td className="small muted">{i.score?.bureau ?? '—'}</td>
                      <td className="num money">{String(i.score?.value ?? '—')}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <Section title={t('cr.explainer')}>
        {explainer.loading ? (
          <Loading />
        ) : explainer.error ? (
          <ErrorBox message={explainer.error} onRetry={explainer.reload} />
        ) : (
          <Explain explain={explainer.data} defaultOpen />
        )}
      </Section>
    </div>
  );
}
