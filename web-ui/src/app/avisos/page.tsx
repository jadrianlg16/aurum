'use client';

/**
 * Inicio › Avisos — `aurum/insights`, for every workspace kind.
 *
 * Three things, in the order you want them: what needs attention now (insights grouped by
 * severity, each with its Explain and the actions the API proposed), what is coming (the
 * deadline calendar, next 90 days), and the digest text — the same string the optional
 * Telegram nudge script (`scripts/telegram_nudges.py`) sends — with a copy button.
 *
 * Dismissing is a real `POST /insights/{ws}/{id}/dismiss`; the row is removed optimistically
 * and the list reloaded, because a dismissed insight is server state, not a local preference.
 *
 * An insight `action.href` comes from the API and is an `/api/...` path — it is rendered as a
 * link, never followed automatically.
 */
import { useCallback, useMemo, useState } from 'react';
import { Empty, ErrorBox, Loading, Money, Section } from '@/components/Bits';
import { Explain } from '@/components/Explain';
import { CopyButton, SeverityBadge, useToast, verifyFlag } from '@/components/Ui3';
import { VerifyChip } from '@/components/VerifyChips';
import { API_BASE, dismissInsight, getDigest, getInsightCalendar, listInsights } from '@/lib/api';
import { daysUntil, formatDate } from '@/lib/format';
import { useHealth, writeGuard } from '@/lib/health';
import { useI18n } from '@/lib/i18n';
import { closePeriod, periodsEndingAt } from '@/lib/period';
import { useResource } from '@/lib/useResource';
import { useWorkspace } from '@/lib/workspace';
import type { Insight, Severity } from '@/lib/types';

const ORDER: Severity[] = ['urgent', 'warn', 'info'];

/** ISO date `days` from today, in UTC — the calendar window, not a money figure. */
function isoOffset(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function AvisosPage() {
  const { t, lang } = useI18n();
  const { ws } = useWorkspace();
  const { demoMode } = useHealth();
  const toast = useToast();
  const [period, setPeriod] = useState(closePeriod());
  const [dismissing, setDismissing] = useState<string | null>(null);

  const insights = useResource(
    useCallback(() => listInsights(ws, { period, lang }), [ws, period, lang]),
    [ws, period, lang],
  );
  const from = useMemo(() => isoOffset(0), []);
  const to = useMemo(() => isoOffset(90), []);
  const calendar = useResource(
    useCallback(() => getInsightCalendar(ws, from, to), [ws, from, to]),
    [ws, from, to],
  );
  const digest = useResource(
    useCallback(() => getDigest(ws, { period, lang }), [ws, period, lang]),
    [ws, period, lang],
  );

  const grouped = useMemo(() => {
    const out: Record<Severity, Insight[]> = { urgent: [], warn: [], info: [] };
    for (const i of insights.data ?? []) out[i.severity].push(i);
    return out;
  }, [insights.data]);

  const dismiss = (id: string) => {
    setDismissing(id);
    insights.set((prev) => (prev ?? []).filter((i) => i.id !== id));
    dismissInsight(ws, id)
      .then(() => {
        toast.show(t('avisos.dismiss'));
        digest.reload();
      })
      .catch(() => insights.reload())
      .finally(() => setDismissing(null));
  };

  return (
    <>
      <div className="page-head">
        <h1>{t('avisos.title')}</h1>
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
        {insights.loading ? (
          <Loading />
        ) : insights.error ? (
          <ErrorBox message={insights.error} onRetry={insights.reload} />
        ) : (insights.data ?? []).length === 0 ? (
          <div className="card">
            <Empty text={t('avisos.none')} />
          </div>
        ) : (
          ORDER.filter((s) => grouped[s].length > 0).map((severity) => (
            <Section
              key={severity}
              title={`${t(`avisos.severity.${severity}`)} · ${grouped[severity].length}`}
            >
              <div className="stack" style={{ gap: 12 }}>
                {grouped[severity].map((i) => (
                  <article key={i.id} className={`insight sev-${i.severity}`}>
                    <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
                      <SeverityBadge severity={i.severity} />
                      <h3 style={{ margin: 0 }}>{i.title}</h3>
                      {verifyFlag(i.body) && <VerifyChip />}
                      <div style={{ flex: 1 }} />
                      {i.amount && (
                        <span className="metric-value sm">
                          <Money value={i.amount} compactCents />
                        </span>
                      )}
                    </div>
                    <p>{i.body}</p>
                    <div className="row small" style={{ gap: 10, flexWrap: 'wrap' }}>
                      {i.due_date && (
                        <span className="muted">
                          {t('avisos.due')}: {formatDate(i.due_date, lang)} ({daysUntil(i.due_date)} d)
                        </span>
                      )}
                      <div style={{ flex: 1 }} />
                      {i.actions.map((a) => (
                        <a
                          key={`${i.id}-${a.href}`}
                          className="btn ghost"
                          href={a.href.startsWith('/api') ? a.href : `${API_BASE}${a.href}`}
                          target="_blank"
                          rel="noreferrer noopener"
                        >
                          {a.label}
                        </a>
                      ))}
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => dismiss(i.id)}
                        disabled={dismissing === i.id}
                        {...writeGuard(demoMode, t('settings.demo.tooltip'))}
                      >
                        {t('avisos.dismiss')}
                      </button>
                    </div>
                    <Explain explain={i.explain} />
                  </article>
                ))}
              </div>
            </Section>
          ))
        )}

        <Section
          title={t('avisos.calendar')}
          actions={
            <span className="small muted">
              {formatDate(from, lang)} → {formatDate(to, lang)}
            </span>
          }
        >
          {calendar.loading ? (
            <Loading />
          ) : calendar.error ? (
            <ErrorBox message={calendar.error} onRetry={calendar.reload} />
          ) : (calendar.data ?? []).length === 0 ? (
            <Empty text={t('avisos.calendar.empty')} />
          ) : (
            <ol className="calendar-strip">
              {(calendar.data ?? []).map((c, idx) => (
                <li key={`${c.kind}-${c.date}-${idx}`} className="cal-item">
                  <time className="cal-date" dateTime={c.date}>
                    {formatDate(c.date, lang, { month: 'short', day: 'numeric' })}
                  </time>
                  <span className="cal-title">
                    {c.title}
                    {c.period ? <span className="muted small"> · {c.period}</span> : null}
                  </span>
                  <span className="cal-days small muted">{daysUntil(c.date)} d</span>
                  {verifyFlag(c.note) && <VerifyChip />}
                </li>
              ))}
            </ol>
          )}
        </Section>

        <Section
          title={t('avisos.digest')}
          actions={
            digest.data ? (
              <CopyButton
                text={digest.data.text}
                label={t('avisos.digest.copy')}
                onDone={(ok) => toast.show(ok ? t('common.copied') : t('common.error'))}
              />
            ) : null
          }
        >
          {digest.loading ? (
            <Loading />
          ) : digest.error ? (
            <ErrorBox message={digest.error} onRetry={digest.reload} />
          ) : !digest.data ? (
            <Empty />
          ) : (
            <>
              <pre className="digest">{digest.data.text}</pre>
              <p className="small muted">
                {t('avisos.severity.urgent')}: {digest.data.urgent_count}
              </p>
            </>
          )}
        </Section>
      </div>

      {toast.node}
    </>
  );
}
