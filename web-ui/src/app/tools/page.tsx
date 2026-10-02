'use client';

/**
 * Tools — MCP status, e.firma vault status, health and sync jobs.
 *
 * The MCP tool list is static: the browser cannot talk to the MCP server, so
 * the screen documents what the server exposes rather than probing it. The port is read from
 * `NEXT_PUBLIC_MCP_PORT` (default 5042), so nothing machine-specific is baked in.
 *
 * The vault card can only ever show *whether* a credential exists — `GET .../vault` never
 * returns material, and this screen never asks for a passphrase.
 */
import { useCallback } from 'react';
import { Empty, ErrorBox, Loading, Section } from '@/components/Bits';
import { API_BASE, getHealth, getVaultStatus, listSyncJobs } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import { MCP_TOOLS } from '@/lib/mcpTools';

const MCP_PORT = process.env.NEXT_PUBLIC_MCP_PORT ?? '5042';

export default function ToolsPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();

  const health = useResource(useCallback(() => getHealth(), []), []);
  const vault = useResource(useCallback(() => getVaultStatus(ws), [ws]), [ws]);
  const jobs = useResource(useCallback(() => listSyncJobs(ws), [ws]), [ws]);

  return (
    <>
      <div className="page-head">
        <h1>{t('tools.title')}</h1>
      </div>

      <div className="stack">
        <Section title={t('tools.mcp')}>
          <div className="row small">
            <span className="rule-chip">
              {t('tools.mcp.port')}: {MCP_PORT}
            </span>
            <span className="rule-chip">AURUM_API_URL → {API_BASE}</span>
            <span className="badge neutral">stdio + HTTP</span>
          </div>
          <h3 style={{ marginTop: 12 }}>{t('tools.mcp.tools')}</h3>
          <table>
            <tbody>
              {MCP_TOOLS.map((x) => (
                <tr key={x.name}>
                  <td className="money" style={{ width: 190 }}>
                    {x.name}
                  </td>
                  <td className="small">{x.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <div className="two-pane">
          <Section title={t('tools.vault')}>
            {vault.loading ? (
              <Loading />
            ) : vault.error ? (
              <ErrorBox message={vault.error} onRetry={vault.reload} />
            ) : (
              <>
                <div className="row">
                  {vault.data?.present ? (
                    <span className="badge pos">{t('tools.vault.configured')}</span>
                  ) : (
                    <span className="badge neutral">{t('tools.vault.absent')}</span>
                  )}
                  {vault.data?.stored_at && (
                    <span className="small muted">{formatDate(vault.data.stored_at.slice(0, 10), lang)}</span>
                  )}
                  {vault.data?.cer_fingerprint && <span className="rule-chip">{vault.data.cer_fingerprint}</span>}
                </div>
                <p className="notice" style={{ marginTop: 10 }}>
                  {t('tools.vault.note')}
                </p>
              </>
            )}

            <h3 style={{ marginTop: 16 }}>{t('tools.jobs')}</h3>
            {jobs.loading ? (
              <Loading />
            ) : jobs.error ? (
              <ErrorBox message={jobs.error} onRetry={jobs.reload} />
            ) : (jobs.data?.length ?? 0) === 0 ? (
              <Empty />
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>{t('common.date')}</th>
                    <th>{t('docs.filter.direction')}</th>
                    <th>{t('common.status')}</th>
                    <th className="num">ZIP</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data!.map((j) => (
                    <tr key={j.id}>
                      <td>{formatDate(j.requested_at.slice(0, 10), lang)}</td>
                      <td>{j.kind}</td>
                      <td>
                        <span className={`badge ${j.status === 'done' ? 'pos' : 'warn'}`}>{j.status}</span>
                      </td>
                      <td className="num">{j.packages}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={t('tools.health')}>
            {health.loading ? (
              <Loading />
            ) : health.error ? (
              <ErrorBox message={health.error} onRetry={health.reload} />
            ) : (
              <>
                <div className="row">
                  <span className={`badge ${health.data?.ok ? 'pos' : 'neg'}`}>{health.data?.ok ? 'ok' : 'down'}</span>
                  {health.data?.version && <span className="rule-chip">{health.data.version}</span>}
                  {health.data?.llm && (
                    <span className="rule-chip">
                      {health.data.llm.provider} · {health.data.llm.model}
                    </span>
                  )}
                </div>
              </>
            )}
          </Section>
        </div>
      </div>
    </>
  );
}
