'use client';

/**
 * "Flujo": the 30/60/90-day balance forecast.
 *
 * The chart is a plain inline SVG whose colours come from
 * the tokens through module CSS classes. Around it: one `Stat` 'Disponible hasta el {date}'
 * from `forecast.safe_to_spend` (same shape as Resumen's), 'Punto más bajo', and 'Colchón'
 * with its hint and an 'Ajustar' dialog (`MoneyInput` or 'Usar el 10 % automático' →
 * `setForecastBuffer(ws, buffer | null)` → reload). The range is a pressed-button group
 * labelled through `tn('common.days', n)`. No commitments → `EmptyState` whose primary switches
 * the page to Pagos fijos through `onGoTo('subs')` (a Link to `?tab=subs` inside `/money/` is a
 * dead control: the page does not remount and `useQueryParam` reads `?tab=` once); the href is
 * only the fallback when the panel is rendered without the page.
 *
 * `toChartNumber` is the single sanctioned float in the app: pixel geometry, never a figure.
 */
import { useCallback, useState } from 'react';
import { Explain } from './Explain';
import { Button, Dialog, EmptyState, ErrorBox, Field, Money, MoneyInput, Skeleton, Stat, useToast } from './ui';
import styles from './money/money.module.css';
import { errorMessage, getForecast, listCommitments, setForecastBuffer } from '@/lib/api';
import { formatAmount, formatDate, toChartNumber } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Commitment, Forecast } from '@/lib/types-organizer';
import { useResource } from '@/lib/useResource';

const RANGES = [30, 60, 90] as const;

export function MoneyFlowPanel({ ws, onGoTo }: { ws: string; onGoTo?: (tab: 'subs') => void }) {
  const { t, tn, lang } = useI18n();
  const toast = useToast();
  const { base } = useMoney();
  const [days, setDays] = useState<number>(90);
  const [adjust, setAdjust] = useState(false);
  const [buffer, setBuffer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fc = useResource<Forecast>(useCallback(() => getForecast(ws, days), [ws, days]), [ws, days]);
  const commitments = useResource<Commitment[]>(useCallback(() => listCommitments(ws), [ws]), [ws]);

  const save = async (auto: boolean) => {
    if (busy) return;
    if (!auto && !/^\d{1,15}(\.\d{1,2})?$/.test(buffer)) {
      setError(t('v.amount'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await setForecastBuffer(ws, auto ? null : buffer);
      setAdjust(false);
      toast.success(t('money.cushion.saved'));
      fc.reload();
    } catch (e) {
      setError(errorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  if (fc.loading || commitments.loading) return <Skeleton variant="card" rows={3} what={t('money.tab.flow')} />;
  if (fc.error) return <ErrorBox error={fc.problem ?? fc.error} onRetry={fc.reload} />;
  const f = fc.data;
  const noCommitments = (commitments.data ?? []).filter((c) => c.status !== 'cancelled').length === 0;
  if (!f || (f.series ?? []).length === 0 || noCommitments) {
    const cta = onGoTo ? { label: t('money.flow.empty_cta'), onClick: () => onGoTo('subs') } : { label: t('money.flow.empty_cta'), href: '/money/?tab=subs' };
    return <EmptyState icon="grid" title={t('money.flow.empty')} primary={cta} compact />;
  }

  const series = f.series;
  const values = series.map((p) => toChartNumber(p.balance));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const W = 720;
  const H = 240;
  const PAD = 8;
  const x = (i: number) => (i / Math.max(1, series.length - 1)) * W;
  const y = (v: number) => H - PAD - ((v - min) / span) * (H - PAD * 2);
  const line = series.map((_, i) => `${x(i).toFixed(2)},${y(values[i]).toFixed(2)}`).join(' ');
  const area = `0,${H} ${line} ${W},${H}`;
  const lowIndex = series.findIndex((p) => p.date === f.low_point?.date);
  const zeroY = y(0);
  const currency = f.buffer?.currency ?? f.safe_to_spend?.currency ?? base;

  return (
    <div className={styles.section} aria-busy={fc.refreshing || undefined}>
      <div className={styles.stats}>
        <div className="card">
          <Stat
            size="lg"
            label={t('money.available_until', { date: formatDate(f.safe_to_spend?.until, lang) })}
            value={<Money amount={f.safe_to_spend?.amount} sign="auto" />}
            explain={f.safe_to_spend?.explain}
          />
        </div>
        <div className="card">
          <Stat label={t('money.flow.low_point')} value={<Money amount={f.low_point?.balance} sign="auto" />} sub={formatDate(f.low_point?.date, lang)} />
        </div>
        <div className="card">
          <Stat
            label={t('money.flow.buffer')}
            value={<Money amount={f.buffer} />}
            sub={
              <span className={styles.toolbar}>
                <span>{t('money.cushion.hint')}</span>
                <Button variant="ghost" onClick={() => setAdjust(true)}>
                  {t('money.cushion.adjust')}
                </Button>
              </span>
            }
          />
        </div>
      </div>

      <section className={styles.section} aria-labelledby="money-flow-title">
        <div className={styles.sectionHead}>
          <h2 id="money-flow-title">{t('money.flow.title')}</h2>
          <div className={['ui-chips', styles.segment].join(' ')} role="group" aria-label={t('money.flow.range')}>
            {RANGES.map((r) => (
              <button key={r} type="button" className="ui-chip" aria-pressed={days === r} onClick={() => setDays(r)}>
                {tn('common.days', r)}
              </button>
            ))}
          </div>
        </div>

        <svg
          className={styles.chart}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={t('money.flow.chart_label', {
            title: t('money.flow.title'),
            low: t('money.flow.low_point'),
            date: formatDate(f.low_point?.date, lang),
            amount: formatAmount(f.low_point?.balance, lang),
          })}
        >
          <polygon points={area} className={styles.chartArea} />
          {min < 0 && <line x1={0} x2={W} y1={zeroY} y2={zeroY} className={styles.chartNeg} strokeWidth={1} strokeDasharray="4 4" />}
          <polyline points={line} fill="none" className={styles.chartLine} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          {lowIndex >= 0 && (
            <g className={styles.chartNeg}>
              <circle cx={x(lowIndex)} cy={y(values[lowIndex])} r={4} />
              <line x1={x(lowIndex)} x2={x(lowIndex)} y1={y(values[lowIndex])} y2={H} strokeWidth={1} strokeDasharray="3 3" />
            </g>
          )}
        </svg>
        <div className={styles.chartFoot}>
          <span>{formatDate(series[0].date, lang)}</span>
          <span>{formatDate(series[series.length - 1].date, lang)}</span>
        </div>

        <Explain explain={f.explain} />
      </section>

      <Dialog
        open={adjust}
        onClose={() => setAdjust(false)}
        title={t('money.cushion.title')}
        size="sm"
        form={{ onSubmit: () => void save(false), busy, submitLabel: t('common.save') }}
        error={error}
      >
        <div className={styles.form}>
          <p className={styles.noticeText}>{t('money.cushion.hint')}</p>
          <Field label={t('money.cushion.amount')}>
            <MoneyInput value={buffer} onChange={setBuffer} currency={currency} focusKey={adjust ? 1 : 0} />
          </Field>
          <div>
            <Button variant="ghost" onClick={() => void save(true)} disabled={busy}>
              {t('money.cushion.auto')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
