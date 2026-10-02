/**
 * The month grid of Calendario — pure, no React, no `Date`
 * at module scope.
 *
 * `buildMonthGrid(period, weekStart, days)` lays every day of the month into 7-column weeks
 * (Monday-first when `weekStart` is 1, Sunday-first when 0), pads with `inMonth:false` filler
 * cells from the neighbouring months, and places the API's sparse `days[]` by ISO date — the
 * API returns only days with items, so laying them consecutively (an earlier bug) put items on
 * the wrong weekday. Weekday indexes come from `new Date(y, m-1, d).getDay()` in LOCAL time,
 * never from `toISOString`.
 */
import type { CalendarDay, CalendarItem } from '@/lib/types-organizer';

export interface GridCell {
  /** `YYYY-MM-DD`. */
  iso: string;
  /** Day of the month (1..31), also for filler cells. */
  day: number;
  inMonth: boolean;
  items: CalendarItem[];
  /** The API's own per-day totals when that day came back, else null. */
  totalOut: CalendarDay['total_out'] | null;
  totalIn: CalendarDay['total_in'] | null;
}

export type WeekStart = 0 | 1;

const pad2 = (n: number): string => String(n).padStart(2, '0');

export function isoOf(y: number, m: number, d: number): string {
  return `${y}-${pad2(m)}-${pad2(d)}`;
}

/** Days in month `m` (1..12) of year `y`. */
export function daysInMonth(y: number, m: number): number {
  return new Date(y, m, 0).getDate();
}

/** Column index (0..6) of an ISO date for the given week start. */
export function columnOf(iso: string, weekStart: WeekStart): number {
  const [y, m, d] = iso.split('-').map(Number);
  const js = new Date(y, m - 1, d).getDay();
  return (js - weekStart + 7) % 7;
}

export function buildMonthGrid(period: string, weekStart: WeekStart, days: CalendarDay[]): GridCell[][] {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7));
  if (!Number.isInteger(y) || !Number.isInteger(m) || m < 1 || m > 12) return [];
  const byIso = new Map<string, CalendarDay>();
  for (const d of days) byIso.set(d.date, d);

  const cellFor = (yy: number, mm: number, dd: number, inMonth: boolean): GridCell => {
    const iso = isoOf(yy, mm, dd);
    const hit = byIso.get(iso);
    return {
      iso,
      day: dd,
      inMonth,
      items: hit?.items ?? [],
      totalOut: hit?.total_out ?? null,
      totalIn: hit?.total_in ?? null,
    };
  };

  const total = daysInMonth(y, m);
  const lead = columnOf(isoOf(y, m, 1), weekStart);
  const cells: GridCell[] = [];

  // Filler from the previous month.
  const prevY = m === 1 ? y - 1 : y;
  const prevM = m === 1 ? 12 : m - 1;
  const prevTotal = daysInMonth(prevY, prevM);
  for (let i = lead - 1; i >= 0; i -= 1) cells.push(cellFor(prevY, prevM, prevTotal - i, false));

  for (let d = 1; d <= total; d += 1) cells.push(cellFor(y, m, d, true));

  // Filler from the next month.
  const nextY = m === 12 ? y + 1 : y;
  const nextM = m === 12 ? 1 : m + 1;
  let nd = 1;
  while (cells.length % 7 !== 0) cells.push(cellFor(nextY, nextM, nd++, false));

  const weeks: GridCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

/**
 * Short weekday headers in grid order, through `Intl` in local time. `2024-01-07` is a Sunday,
 * so `Jan 7 + jsIndex` is the weekday with that `getDay()`.
 */
export function weekdayHeaders(weekStart: WeekStart, locale: string): string[] {
  let fmt: Intl.DateTimeFormat | null = null;
  try {
    fmt = new Intl.DateTimeFormat(locale, { weekday: 'short' });
  } catch {
    fmt = null;
  }
  return Array.from({ length: 7 }, (_, i) => {
    const js = (weekStart + i) % 7;
    const d = new Date(2024, 0, 7 + js);
    return fmt ? fmt.format(d) : String(js);
  });
}

/** Tax items never render in the personal calendar; everything else stays. */
export function dropTax(days: CalendarDay[]): CalendarDay[] {
  return days.map((d) => ({ ...d, items: d.items.filter((it) => it.kind !== 'tax') })).filter((d) => d.items.length > 0);
}
