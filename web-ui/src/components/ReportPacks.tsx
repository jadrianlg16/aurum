'use client';

/**
 * Report packs — `aurum/reports`.
 *
 * The catalog says which packs apply to the workspace and whether each one takes a month, a
 * year or no period at all; the picker follows that instead of always asking for a month.
 *
 * Preview has two forms and both are here because they answer different questions:
 *  - `/{pack}/preview` returns the structured report (sections → kpis / tables / explains),
 *    which is what you read to check a figure;
 *  - `/{pack}?format=html` returns the rendered document, shown in a sandboxed iframe via
 *    `srcDoc` — fetched through the API client so the bearer token applies, and sandboxed
 *    because it is API-generated HTML rendered inside the app.
 *
 * The PDF is a plain link (a download, never a fetch). "Archivar" POSTs and then relists;
 * a pack that has never been archived answers 404, which is the empty state, not an error.
 */
import { useCallback, useState } from 'react';
import { Empty, ErrorBox, Loading, Section } from './Bits';
import { CitationCard } from './Explain';
import { CopyButton, type Toaster } from './Ui3';
import {
  ApiError,
  archiveReport,
  errorMessage,
  getReportCatalog,
  getReportHtml,
  getReportPreview,
  listArchivedReports,
  reportPdfUrl,
} from '@/lib/api';
import { formatDate } from '@/lib/format';
import { useHealth, writeGuard } from '@/lib/health';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import type { ArchivedReport, ReportPack, ReportPreview } from '@/lib/types';

function periodFor(pack: ReportPack | null, month: string, year: string): string | undefined {
  if (!pack) return undefined;
  if (pack.period_kind === 'month') return month;
  if (pack.period_kind === 'year') return year;
  return undefined;
}

export function ReportPacksPanel({ ws, toast }: { ws: string; toast: Toaster }) {
  const { t, lang } = useI18n();
  const { demoMode } = useHealth();
  const catalog = useResource(useCallback(() => getReportCatalog(ws), [ws]), [ws]);
  const [packId, setPackId] = useState<string>('monthly-review');
  const [month, setMonth] = useState(closePeriod());
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [archive, setArchive] = useState<ArchivedReport[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const pack = (catalog.data?.packs ?? []).find((p) => p.pack === packId) ?? null;
  const period = periodFor(pack, month, year);

  const run = <T,>(tag: string, p: Promise<T>, ok: (v: T) => void) => {
    setBusy(tag);
    setErr(null);
    p.then(ok)
      .catch((e: unknown) => setErr(errorMessage(e)))
      .finally(() => setBusy(null));
  };

  const loadArchive = useCallback(() => {
    setErr(null);
    listArchivedReports(ws, packId)
      .then(setArchive)
      // 404 = this pack has never been archived. That is an empty list, not a failure.
      .catch((e: unknown) => (e instanceof ApiError && e.status === 404 ? setArchive([]) : setErr(errorMessage(e))));
  }, [ws, packId]);

  if (catalog.loading) return <Loading />;
  if (catalog.error) return <ErrorBox message={catalog.error} onRetry={catalog.reload} />;
  if (!catalog.data) return <Empty />;

  return (
    <div className="stack">
      <Section title={t('packs.title')}>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field">
            {t('packs.pack')}
            <select
              value={packId}
              onChange={(e) => {
                setPackId(e.target.value);
                setPreview(null);
                setHtml(null);
                setArchive(null);
              }}
            >
              {catalog.data.packs.map((p) => (
                <option key={p.pack} value={p.pack} disabled={!p.applicable}>
                  {p.title[lang] ?? p.title.es}
                  {p.applicable ? '' : ` — ${t('packs.not_applicable')}`}
                </option>
              ))}
            </select>
          </label>

          {pack?.period_kind === 'month' && (
            <label className="field">
              {t('common.period')}
              <select value={month} onChange={(e) => setMonth(e.target.value)}>
                {periodsEndingAt(closePeriod(), 12).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
          )}
          {pack?.period_kind === 'year' && (
            <label className="field">
              {t('common.period')}
              <input
                inputMode="numeric"
                value={year}
                onChange={(e) => setYear(e.target.value.replace(/[^0-9]/g, '').slice(0, 4))}
              />
            </label>
          )}

          <button
            type="button"
            className="btn primary"
            disabled={busy !== null || !pack?.applicable}
            onClick={() =>
              run('preview', getReportPreview(ws, packId, { period, lang }), (p) => {
                setPreview(p);
                setHtml(null);
              })
            }
          >
            {t('packs.preview')}
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy !== null || !pack?.applicable}
            onClick={() => run('html', getReportHtml(ws, packId, { period, lang }), setHtml)}
          >
            {t('packs.preview.html')}
          </button>
          <a
            className="btn"
            href={reportPdfUrl(ws, packId, { period, lang })}
            target="_blank"
            rel="noreferrer noopener"
          >
            {t('packs.download')}
          </a>
          <button
            type="button"
            className="btn"
            disabled={busy !== null || !pack?.applicable}
            {...writeGuard(demoMode, t('settings.demo.tooltip'))}
            onClick={() =>
              run('archive', archiveReport(ws, packId, { period, lang, format: 'pdf' }), () => {
                toast.show(t('packs.archived_ok'));
                loadArchive();
              })
            }
          >
            {t('packs.archive')}
          </button>
          <button type="button" className="btn ghost" onClick={loadArchive}>
            {t('packs.archive_list')}
          </button>
        </div>
        {err && <p className="err">{err}</p>}
      </Section>

      {preview && <ReportPreviewView preview={preview} toast={toast} />}

      {html !== null && (
        <Section title={t('packs.preview.html')}>
          {/* API-generated HTML: sandboxed, no scripts, no same-origin access. */}
          <iframe className="report-frame" title={t('packs.preview.html')} sandbox="" srcDoc={html} />
        </Section>
      )}

      {archive !== null && (
        <Section title={t('packs.archive_list')}>
          {archive.length === 0 ? (
            <Empty text={t('packs.no_archive')} />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('packs.archived_at')}</th>
                    <th>{t('common.period')}</th>
                    <th>{t('packs.format')}</th>
                    <th>{t('packs.sha')}</th>
                    <th className="num">{t('packs.size')}</th>
                  </tr>
                </thead>
                <tbody>
                  {archive.map((a) => (
                    <tr key={a.id}>
                      <td>{formatDate(a.created_at.slice(0, 10), lang)}</td>
                      <td>{a.period ?? '—'}</td>
                      <td>{a.format}</td>
                      <td className="mono small">{a.sha256.slice(0, 16)}…</td>
                      <td className="num">{a.size ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

function ReportPreviewView({ preview, toast }: { preview: ReportPreview; toast: Toaster }) {
  const { t, lang } = useI18n();
  return (
    <Section
      title={preview.title}
      actions={
        <div className="row" style={{ gap: 6 }}>
          {preview.draft && <span className="badge warn">{preview.watermark_text ?? t('packs.draft')}</span>}
          <CopyButton
            text={preview.sections
              .map((s) => `${s.title}\n${s.kpis.map((k) => `  ${k.label}: ${k.value}`).join('\n')}`)
              .join('\n\n')}
            onDone={(ok) => toast.show(ok ? t('common.copied') : t('common.error'))}
          />
        </div>
      }
    >
      <p className="small muted">
        {t('packs.generated')}: {formatDate(preview.generated_at.slice(0, 10), lang)} ·{' '}
        {preview.sections.length} {t('packs.preview.sections')}
      </p>

      {preview.warnings.length > 0 && (
        <ul className="warn-list">
          {preview.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <div className="stack">
        {preview.sections.map((s) => (
          <div key={s.title} className="report-section">
            <h3>{s.title}</h3>
            {s.kpis.length > 0 && (
              <div className="grid cols-4">
                {s.kpis.map((k) => (
                  <div key={k.label}>
                    <div className="metric-label">{k.label}</div>
                    {/* `value` is a preformatted string from the API — printed verbatim. */}
                    <div className="metric-value sm money">{k.value}</div>
                    {k.note && <div className="small muted">{k.note}</div>}
                  </div>
                ))}
              </div>
            )}
            {s.tables.map((tb, i) => (
              <div className="table-scroll" key={`${s.title}-t${i}`}>
                {tb.title && <h4>{tb.title}</h4>}
                <table>
                  <thead>
                    <tr>
                      {tb.columns.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tb.rows.map((row, ri) => (
                      <tr key={`${s.title}-r${ri}`}>
                        {row.map((cell, ci) => (
                          <td key={`${s.title}-r${ri}c${ci}`} className={ci === 0 ? '' : 'num money'}>
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {s.notes.map((n) => (
              <p className="small muted" key={n}>
                {n}
              </p>
            ))}
            {s.explains.map((e, i) => (
              <div className="explain" key={`${s.title}-e${i}`}>
                <p className="explain-summary">{e.summary}</p>
                {e.steps.length > 0 && (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('explain.step')}</th>
                          <th className="num">{t('explain.value')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {e.steps.map((st, si) => (
                          <tr key={`${st.label}-${si}`}>
                            <td>{st.label}</td>
                            <td className="num money">{st.value}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {e.citations.map((c, ci) => (
                  <CitationCard key={`${c.law}-${c.article}-${ci}`} citation={c} />
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>

      {preview.rule_versions.length > 0 && (
        <div className="row small muted" style={{ marginTop: 10 }}>
          <span>{t('explain.rule_versions')}:</span>
          {preview.rule_versions.map((r) => (
            <span key={r} className="rule-chip">
              {r}
            </span>
          ))}
        </div>
      )}
    </Section>
  );
}
