'use client';

/**
 * Watch — the law-change feed, the watched sources and the rule proposals.
 *
 * The sources tab: each source shows how it is fetched and how
 * often, and opens a drawer with `GET /watch/sources/{id}/history` — the snapshots actually
 * taken (fetch time, content hash, size) and the changes they produced. A source with no
 * snapshot yet says so rather than looking broken; that is the normal state offline.
 */
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Section } from '@/components/Bits';
import { getChanges, getWatchSourceHistory, listWatchProposals, listWatchSources } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { useQueryTab } from '@/lib/query';
import { useResource } from '@/lib/useResource';
import type { WatchSource } from '@/lib/types';

type Tab = 'feed' | 'sources' | 'proposals';

const TAB_KEY: Record<Tab, MsgKey> = {
  feed: 'watch.tab.feed',
  sources: 'watch.tab.sources',
  proposals: 'watch.tab.proposals',
};

/** Fetch methods differ in how much they can be trusted to be complete; the badge says which. */
const METHOD_TONE: Record<string, string> = {
  bulk: 'gold',
  api: 'info',
  rss: 'info',
  html: 'warn',
};

function HistoryDrawer({ source, onClose }: { source: WatchSource; onClose: () => void }) {
  const { t, lang } = useI18n();
  const history = useResource(
    useCallback(() => getWatchSourceHistory(source.id), [source.id]),
    [source.id],
  );

  return (
    <aside className="card">
      <div className="row">
        <h2 style={{ margin: 0 }}>{t('watch.history')}</h2>
        <div style={{ flex: 1 }} />
        <button type="button" className="btn ghost" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>
      <p className="small muted">{source.name}</p>

      {history.loading ? (
        <Loading />
      ) : history.error ? (
        <ErrorBox message={history.error} onRetry={history.reload} />
      ) : (history.data?.snapshots.length ?? 0) === 0 ? (
        <Empty text={t('watch.no_history')} />
      ) : (
        <>
          <h3>{t('watch.snapshots')}</h3>
          <div className="table-scroll" style={{ maxHeight: 280, overflowY: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>{t('watch.fetched_at')}</th>
                  <th>{t('watch.hash')}</th>
                  <th className="num">{t('watch.bytes')}</th>
                </tr>
              </thead>
              <tbody>
                {history.data!.snapshots.map((s) => (
                  <tr key={`${s.source_id}-${s.fetched_at}`}>
                    <td className="small">{s.fetched_at.replace('T', ' ').slice(0, 19)}</td>
                    <td className="small" style={{ fontFamily: 'var(--mono)' }}>
                      {s.content_hash.slice(0, 12)}…
                    </td>
                    <td className="num money">{s.bytes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {(history.data?.changes.length ?? 0) > 0 && (
        <>
          <h3 style={{ marginTop: 12 }}>{t('watch.feed')}</h3>
          <div className="stack" style={{ gap: 8 }}>
            {history.data!.changes.map((c) => (
              <div key={c.id} className="small">
                <strong>{c.summary}</strong>
                <div className="muted">
                  {t('watch.detected')} {formatDate(c.detected_at.slice(0, 10), lang)}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

export default function WatchPage() {
  const { t, lang } = useI18n();
  const [tab, setTab] = useQueryTab<Tab>(['feed', 'sources', 'proposals'] as const, 'feed');
  const [openSource, setOpenSource] = useState<WatchSource | null>(null);

  const changes = useResource(useCallback(() => getChanges(), []), []);
  const sources = useResource(useCallback(() => listWatchSources(), []), []);
  const proposals = useResource(useCallback(() => listWatchProposals(), []), []);

  return (
    <>
      <div className="page-head">
        <h1>{t('watch.title')}</h1>
      </div>

      <div className="tabs" role="tablist">
        {(['feed', 'sources', 'proposals'] as Tab[]).map((x) => (
          <button key={x} type="button" role="tab" aria-selected={tab === x} onClick={() => setTab(x)}>
            {t(TAB_KEY[x])}
          </button>
        ))}
      </div>

      {tab === 'feed' && (
        <Section title={t('watch.feed')}>
          {changes.loading ? (
            <Loading />
          ) : changes.error ? (
            <ErrorBox message={changes.error} onRetry={changes.reload} />
          ) : (changes.data?.length ?? 0) === 0 ? (
            <Empty />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {changes.data!.map((c) => (
                <div key={c.id} className="card">
                  <div className="row">
                    <span className="badge gold">{sources.data?.find((s) => s.id === c.source_id)?.name ?? c.source_id}</span>
                    <div style={{ flex: 1 }} />
                    <span className="small muted">
                      {t('watch.detected')} {formatDate(c.detected_at.slice(0, 10), lang)}
                    </span>
                    {c.effective_from && (
                      <span className="badge neutral">
                        {t('watch.effective')} {formatDate(c.effective_from, lang)}
                      </span>
                    )}
                  </div>
                  <p className="small" style={{ margin: '8px 0 6px' }}>
                    {c.summary}
                  </p>
                  {c.domains.length > 0 && (
                    <div className="row small">
                      <span className="muted">{t('watch.domains')}:</span>
                      {c.domains.map((d) => (
                        <span key={d} className="badge info">
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {tab === 'sources' && (
        <div className={openSource ? 'grid cols-2' : ''}>
          <Section title={t('watch.sources')}>
            {sources.loading ? (
              <Loading />
            ) : sources.error ? (
              <ErrorBox message={sources.error} onRetry={sources.reload} />
            ) : (sources.data?.length ?? 0) === 0 ? (
              <Empty />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t('common.name')}</th>
                      <th>{t('watch.jurisdiction')}</th>
                      <th>{t('watch.doc_type')}</th>
                      <th>{t('watch.fetch_method')}</th>
                      <th>{t('watch.cadence')}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {sources.data!.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <strong>{s.name}</strong>
                          <div className="small muted" style={{ fontFamily: 'var(--mono)' }}>
                            {s.id}
                          </div>
                          {s.domains && s.domains.length > 0 && (
                            <div className="row small" style={{ flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                              {s.domains.map((d) => (
                                <span key={d} className="badge info">
                                  {d}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>
                          <span className="badge neutral">{s.jurisdiction}</span>
                        </td>
                        <td className="small">{s.doc_type}</td>
                        <td>
                          <span className={`badge ${METHOD_TONE[s.fetch_method] ?? 'neutral'}`}>
                            {s.fetch_method}
                          </span>
                        </td>
                        <td className="small">{s.cadence}</td>
                        <td>
                          <button type="button" className="btn ghost" onClick={() => setOpenSource(s)}>
                            {t('watch.history')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {openSource && <HistoryDrawer source={openSource} onClose={() => setOpenSource(null)} />}
        </div>
      )}

      {tab === 'proposals' && (
        <Section title={t('watch.proposals')}>
          {proposals.loading ? (
            <Loading />
          ) : proposals.error ? (
            <ErrorBox message={proposals.error} onRetry={proposals.reload} />
          ) : (proposals.data?.length ?? 0) === 0 ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('explain.rule_versions')}</th>
                    <th>{t('watch.proposal.field')}</th>
                    <th>{t('watch.proposal.from')}</th>
                    <th>{t('watch.proposal.to')}</th>
                    <th>{t('common.status')}</th>
                    <th>{t('common.date')}</th>
                  </tr>
                </thead>
                <tbody>
                  {proposals.data!.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <span className="rule-chip">{p.rule_id}</span>
                      </td>
                      <td className="small">{p.field}</td>
                      <td className="small">{p.old_value}</td>
                      <td className="small">
                        <strong>{p.new_value}</strong>
                      </td>
                      <td>
                        <span className={`badge ${p.status === 'proposed' ? 'warn' : 'neutral'}`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="small muted">{formatDate(p.created_at.slice(0, 10), lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </>
  );
}
