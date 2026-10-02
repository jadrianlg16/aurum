'use client';

/**
 * Reconcile — the bank lines of a period against ledger transactions and CFDIs, with
 * match/unmatch actions.
 *
 * Wired to:
 *   • `GET  /api/ingest/{ws}/reconcile?period=`      → the board
 *   • `POST /api/ingest/{ws}/reconcile/match`        `{bank_line_id, txn_id?, cfdi_uuid?}`
 *   • `POST /api/ingest/{ws}/reconcile/unmatch`      `{bank_line_id}`
 * The match endpoints return the refreshed board, and the screen also re-fetches after every
 * write so nothing on screen is an optimistic guess.
 *
 * Suggestions come from the API with their own score; the UI never invents a match — a chip is
 * one click on a candidate the engine proposed, and anything unmatched still links to the
 * Inbox, where a document can be accepted into the ledger.
 */
import { useCallback, useState } from 'react';
import Link from 'next/link';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { errorMessage, getReconcile, matchBankLine, unmatchBankLine } from '@/lib/api';
import { formatDate, formatPct } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';

export default function ReconcilePage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();
  const [period, setPeriod] = useState(closePeriod());
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);

  const board = useResource(useCallback(() => getReconcile(ws, period), [ws, period]), [ws, period]);

  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id);
    setWriteError(null);
    try {
      await fn();
      board.reload();
    } catch (e) {
      setWriteError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const lines = board.data?.bank_lines ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('rec.title')}</h1>
          <div className="sub">{t('rec.board')}</div>
        </div>
        <div className="spacer" />
        <div className="row">
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
          <button type="button" className="btn" onClick={board.reload}>
            {t('rec.refresh')}
          </button>
          <span className="badge neg">
            {t('rec.unmatched_bank')}: {board.data?.unmatched_bank ?? 0}
          </span>
          <span className="badge warn">
            {t('rec.unmatched_cfdi')}: {board.data?.unmatched_cfdi.length ?? 0}
          </span>
        </div>
      </div>

      <p className="notice" style={{ marginBottom: 14 }}>
        {t('rec.pending_backend')}{' '}
        <Link href="/inbox" className="btn ghost" style={{ padding: '0 4px' }}>
          {t('nav.inbox')} →
        </Link>
      </p>
      {writeError && <p className="err">{writeError}</p>}

      {board.loading ? (
        <Loading />
      ) : board.error ? (
        <ErrorBox message={board.error} onRetry={board.reload} />
      ) : (
        <div className="stack">
          <Section title={t('rec.bank')}>
            {lines.length === 0 ? (
              <Empty />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t('common.date')}</th>
                      <th>{t('common.description')}</th>
                      <th className="num">{t('common.amount')}</th>
                      <th>{t('common.status')}</th>
                      <th>{t('rec.suggestions')}</th>
                      <th className="num">{t('common.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((b) => {
                      const matched = Boolean(b.matched_txn_id || b.cfdi_uuid);
                      return (
                        <tr key={b.id} className={matched ? '' : 'selected'}>
                          <td>{formatDate(b.date, lang)}</td>
                          <td>{b.description}</td>
                          <td className="num">
                            <Money value={b.amount} sign />
                          </td>
                          <td>
                            {matched ? (
                              <span className="badge pos" title={b.matched_txn_id ?? b.cfdi_uuid ?? ''}>
                                {t('rec.matched')}
                              </span>
                            ) : (
                              <span className="badge neg">{t('rec.unmatched_bank')}</span>
                            )}
                          </td>
                          <td>
                            {matched || b.suggestions.length === 0 ? (
                              <span className="muted small">{t('rec.no_suggestions')}</span>
                            ) : (
                              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                                {b.suggestions.map((s, i) => (
                                  <button
                                    key={`${s.txn_id ?? s.cfdi_uuid ?? i}`}
                                    type="button"
                                    className="rule-chip"
                                    disabled={busy === b.id}
                                    title={s.txn_id ?? s.cfdi_uuid ?? ''}
                                    onClick={() =>
                                      void act(b.id, () =>
                                        matchBankLine(ws, {
                                          bank_line_id: b.id,
                                          ...(s.txn_id ? { txn_id: s.txn_id } : {}),
                                          ...(s.cfdi_uuid ? { cfdi_uuid: s.cfdi_uuid } : {}),
                                        }),
                                      )
                                    }
                                  >
                                    {(s.txn_id ?? s.cfdi_uuid ?? '').slice(0, 12)}… · {formatPct(s.score, lang)}
                                  </button>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="num">
                            {matched ? (
                              <button
                                type="button"
                                className="btn ghost"
                                disabled={busy === b.id}
                                onClick={() => void act(b.id, () => unmatchBankLine(ws, b.id))}
                              >
                                {t('rec.unmatch')}
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn"
                                disabled={busy === b.id || b.suggestions.length === 0}
                                onClick={() => {
                                  const s = b.suggestions[0];
                                  if (!s) return;
                                  void act(b.id, () =>
                                    matchBankLine(ws, {
                                      bank_line_id: b.id,
                                      ...(s.txn_id ? { txn_id: s.txn_id } : {}),
                                      ...(s.cfdi_uuid ? { cfdi_uuid: s.cfdi_uuid } : {}),
                                    }),
                                  );
                                }}
                              >
                                {t('rec.match')}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {board.data?.explain && <Explain explain={board.data.explain} />}
          </Section>

          <Section title={t('rec.unmatched_cfdi')}>
            {(board.data?.unmatched_cfdi.length ?? 0) === 0 ? (
              <Empty />
            ) : (
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                {board.data!.unmatched_cfdi.map((u) => (
                  <span key={u} className="badge warn money">
                    {u.slice(0, 18)}…
                  </span>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}
    </>
  );
}
