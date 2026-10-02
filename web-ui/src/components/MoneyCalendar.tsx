'use client';

/**
 * "Calendario": `MonthPicker` bound to `?period=`
 * (`usePeriodParam`), `GET /calendar?from&to` over `monthBounds(period)`, the grid built
 * client-side by `money/monthGrid.ts` (Monday-first es / Sunday-first en, every day
 * rendered, API days placed by ISO date), today from `todayLocalIso()` after mount, tax items
 * dropped unconditionally. ≥768px → `CalendarGrid` (cell → day Sheet → OccurrenceSheet);
 * below → `AgendaList` (row → OccurrenceSheet). Month strip 'Sale $X · Entra $Y' from the
 * API's `totals` when present, else `lib/validate.sumDecimals` over the per-day totals (the
 * only client-side sum this screen is allowed).
 *
 * The legacy `toast` prop is accepted and ignored (new panels use `components/ui` `useToast`).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Explain } from './Explain';
import { EmptyState, ErrorBox, MonthPicker, Money, Sheet, Skeleton } from './ui';
import { AgendaList, AgendaRow } from './money/AgendaList';
import { CalendarGrid } from './money/CalendarGrid';
import { buildMonthGrid, dropTax, weekdayHeaders, type GridCell, type WeekStart } from './money/monthGrid';
import { OccurrenceSheet } from './money/OccurrenceSheet';
import styles from './money/money.module.css';
import { getOrganizerCalendar, listCommitments } from '@/lib/api';
import { formatDate, formatPeriod, todayLocalIso } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import { monthBounds, usePeriodParam } from '@/lib/period';
import type { Amount } from '@/lib/types';
import type { CalendarItem, Commitment, OrganizerCalendar } from '@/lib/types-organizer';
import { useResource } from '@/lib/useResource';
import { sumDecimals } from '@/lib/validate';

const GRID_QUERY = '(min-width: 768px)';

/** True at ≥768px; `null` until the first measurement after mount (agenda renders meanwhile). */
function useWide(): boolean | null {
  const [wide, setWide] = useState<boolean | null>(null);
  useEffect(() => {
    const mq = window.matchMedia(GRID_QUERY);
    const apply = () => setWide(mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);
  return wide;
}

type CalendarWithTotals = OrganizerCalendar & { totals?: { out: Amount; in: Amount } | null };

export function MoneyCalendarPanel({ ws }: { ws: string; toast?: unknown }) {
  const { t, lang } = useI18n();
  const { base } = useMoney();
  const [period, setPeriod] = usePeriodParam();
  const { from, to } = monthBounds(period);
  const wide = useWide();
  const [today, setToday] = useState<string | null>(null);
  const [dayIso, setDayIso] = useState<string | null>(null);
  const [item, setItem] = useState<CalendarItem | null>(null);

  useEffect(() => {
    setToday(todayLocalIso());
  }, [period]);

  const cal = useResource<CalendarWithTotals>(useCallback(() => getOrganizerCalendar(ws, from, to), [ws, from, to]), [ws, from, to]);
  const commitments = useResource<Commitment[]>(useCallback(() => listCommitments(ws), [ws]), [ws]);
  const byId = useMemo(() => new Map((commitments.data ?? []).map((c) => [c.id, c])), [commitments.data]);

  const days = useMemo(() => dropTax(cal.data?.days ?? []), [cal.data]);
  const weekStart: WeekStart = lang === 'es' ? 1 : 0;
  const weeks = useMemo(() => buildMonthGrid(period, weekStart, days), [period, weekStart, days]);
  const headers = useMemo(() => weekdayHeaders(weekStart, lang === 'es' ? 'es-MX' : 'en-US'), [weekStart, lang]);

  const totals = useMemo(() => {
    if (cal.data?.totals) return cal.data.totals;
    // The strip only renders with days present; the workspace base currency is the last resort.
    const currency = days[0]?.total_out.currency ?? days[0]?.total_in.currency ?? base;
    return {
      out: { amount: sumDecimals(days.map((d) => d.total_out.amount)), currency },
      in: { amount: sumDecimals(days.map((d) => d.total_in.amount)), currency },
    };
  }, [cal.data, days, base]);

  const reload = () => cal.reload();
  // The day sheet stays open under the occurrence dialog, so Esc walks back cell ← sheet ← item.
  const pick = (it: CalendarItem) => setItem(it);
  const linked = item ? byId.get(item.id) : undefined;
  const dayItems = dayIso ? days.find((d) => d.date === dayIso)?.items ?? [] : [];

  const monthLabel = formatPeriod(period, lang, 'long');

  return (
    <div className={styles.section}>
      <div className={styles.toolbar}>
        <MonthPicker value={period} onChange={setPeriod} />
        <span className={styles.grow} />
        {days.length > 0 && (
          <div className={styles.strip} aria-live="polite">
            <span>
              {t('money.cal.sale')} <Money amount={totals.out} />
            </span>
            <span aria-hidden="true">·</span>
            <span>
              {t('money.cal.entra')} <Money amount={totals.in} />
            </span>
          </div>
        )}
      </div>

      {cal.loading ? (
        <Skeleton variant="card" rows={4} what={t('money.tab.calendar')} />
      ) : cal.error ? (
        <ErrorBox error={cal.problem ?? cal.error} onRetry={cal.reload} />
      ) : days.length === 0 ? (
        <EmptyState icon="calendar" title={t('money.cal.empty', { period: monthLabel })} body={t('money.cal.empty.body')} compact />
      ) : wide ? (
        <CalendarGrid weeks={weeks} headers={headers} today={today} onPickDay={(cell: GridCell) => setDayIso(cell.iso)} />
      ) : (
        <AgendaList days={days} today={today} onPick={pick} />
      )}

      <Explain explain={cal.data?.explain} />

      <Sheet open={dayIso !== null} onClose={() => setDayIso(null)} title={dayIso ? formatDate(dayIso, lang, 'weekday') : ''}>
        {dayIso && (
          <ul className={styles.dayList}>
            {dayItems.length === 0 && <li className={styles.noticeMeta}>{t('money.cal.nothing_today')}</li>}
            {dayItems.map((it) => (
              <li key={`${it.kind}-${it.id}-${it.date}`} className={styles.agendaItems}>
                <AgendaRow item={it} onPick={pick} />
              </li>
            ))}
          </ul>
        )}
      </Sheet>

      <OccurrenceSheet
        ws={ws}
        item={item}
        labelId={linked?.label_id ?? null}
        amountVariable={item?.amount_variable ?? linked?.amount_variable ?? null}
        onClose={() => setItem(null)}
        onChanged={reload}
      />
    </div>
  );
}
