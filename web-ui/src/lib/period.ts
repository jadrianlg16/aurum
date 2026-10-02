/**
 * Period helpers. A "period" is a `YYYY-MM` string, exactly as the tax and pf APIs use it.
 *
 * The default period everywhere is the *previous* month, because that is the month you close:
 * the MX monthly return for month M is due on the 17th of M+1, so on any given day the
 * interesting period is the one that just ended. Nothing here is machine-specific — it reads
 * the browser clock, which the screenshot script freezes only by choosing URLs, not dates.
 */
import { formatPeriod } from './format';
import { useQueryParam } from './query';
import type { Lang } from './types';
import { PERIOD_RE } from './validate';

export function periodOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function currentPeriod(now = new Date()): string {
  return periodOf(now);
}

export function previousPeriod(period: string): string {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1;
  const d = new Date(Date.UTC(y, m - 1, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function nextPeriod(period: string): string {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1;
  const d = new Date(Date.UTC(y, m + 1, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** The month to close: the one that just ended. */
export function closePeriod(now = new Date()): string {
  return previousPeriod(currentPeriod(now));
}

/** First and last day of a period, for journal range filters. */
export function periodRange(period: string): { start: string; end: string } {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7));
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return { start: `${period}-01`, end: `${period}-${String(last).padStart(2, '0')}` };
}

/** `count` periods ending at `period`, oldest first — for the period picker. */
export function periodsEndingAt(period: string, count: number): string[] {
  const out: string[] = [period];
  for (let i = 1; i < count; i += 1) out.unshift(previousPeriod(out[0]));
  return out;
}

/**
 * The next occurrence of a day-of-month on or after `from`, as an ISO date. Used for credit
 * card cut/due dates, which the API gives as a day number.
 */
export function nextDayOfMonth(day: number, from = new Date()): string {
  const y = from.getFullYear();
  const m = from.getMonth();
  const candidate = new Date(y, m, day);
  const target = candidate >= new Date(y, m, from.getDate()) ? candidate : new Date(y, m + 1, day);
  return `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(
    target.getDate(),
  ).padStart(2, '0')}`;
}

/* ---------------------------------------------------------- URL period ---- */
/*
 * `?period=YYYY-MM` is shared by Home, Movimientos and Presupuesto, and the
 * default is `currentPeriod()` in LOCAL time (never `toISOString`, which at 23:30 in
 * Mexico City already says tomorrow / next month). `closePeriod` above is NOT renamed;
 * personal pages simply stop importing it.
 */

/** `period ± n` months, e.g. `shiftPeriod('2026-01', -1) === '2025-12'`. Pure month math. */
export function shiftPeriod(period: string, n: number): string {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1;
  const d = new Date(Date.UTC(y, m + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** First and last day of the month as ISO dates — the `from`/`to` of an entries query. */
export function monthBounds(period: string): { from: string; to: string } {
  const { start, end } = periodRange(period);
  return { from: start, to: end };
}

/** The human label ("septiembre 2026"), delegating to `format.formatPeriod`. Call after mount. */
export function periodLabel(period: string, lang: Lang): string {
  return formatPeriod(period, lang);
}

/**
 * `[period, setPeriod]` synced with `?period=`: starts at `currentPeriod()` (what the server
 * rendered), applies a valid `?period=` once after mount, and writes changes back with
 * `replaceState`. Pages render the value only after mount (no `Date` at prerender).
 */
export function usePeriodParam(): [string, (next: string) => void] {
  return useQueryParam('period', currentPeriod(), (v) => PERIOD_RE.test(v));
}
