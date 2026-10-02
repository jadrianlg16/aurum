import { describe, expect, it } from 'vitest';
import { buildMonthGrid, columnOf, dropTax, weekdayHeaders } from './monthGrid';
import type { CalendarDay, CalendarItem } from '@/lib/types-organizer';

const item = (id: string, date: string, kind: CalendarItem['kind'] = 'commitment'): CalendarItem => ({
  kind,
  date,
  id,
  name: id,
  amount: { amount: '100.00', currency: 'MXN' },
  status: 'upcoming',
});

const day = (date: string, items: CalendarItem[]): CalendarDay => ({
  date,
  items,
  total_out: { amount: '100.00', currency: 'MXN' },
  total_in: { amount: '0.00', currency: 'MXN' },
});

// 2026-09-01 is a Tuesday (tests/setup.ts pins TZ=America/Mexico_City; the maths is local).
describe('buildMonthGrid', () => {
  const sparse = [day('2026-09-05', [item('a', '2026-09-05')]), day('2026-09-08', [item('b', '2026-09-08')])];

  it('es (Monday-first): day 5 lands in column 5 (sáb), day 8 in column 1 (mar), 5×7 cells', () => {
    const weeks = buildMonthGrid('2026-09', 1, sparse);
    expect(weeks).toHaveLength(5);
    expect(weeks.every((w) => w.length === 7)).toBe(true);
    const flat = weeks.flat();
    const d5 = flat.findIndex((c) => c.iso === '2026-09-05');
    const d8 = flat.findIndex((c) => c.iso === '2026-09-08');
    expect(d5 % 7).toBe(5);
    expect(d8 % 7).toBe(1);
    expect(flat[d5].items.map((i) => i.id)).toEqual(['a']);
    expect(flat[d8].items.map((i) => i.id)).toEqual(['b']);
    expect(weekdayHeaders(1, 'es-MX')[5].toLowerCase()).toMatch(/^s[aá]b/);
    expect(weekdayHeaders(1, 'es-MX')[1].toLowerCase()).toMatch(/^mar/);
  });

  it('en (Sunday-first): day 5 lands in column 6, still 5 weeks', () => {
    const weeks = buildMonthGrid('2026-09', 0, sparse);
    expect(weeks).toHaveLength(5);
    const flat = weeks.flat();
    expect(flat.findIndex((c) => c.iso === '2026-09-05') % 7).toBe(6);
    expect(weekdayHeaders(0, 'en-US')[0].toLowerCase()).toMatch(/^sun/);
  });

  it('renders every day of the month once and pads with out-of-month filler cells', () => {
    const weeks = buildMonthGrid('2026-09', 1, []);
    const flat = weeks.flat();
    const inMonth = flat.filter((c) => c.inMonth);
    expect(inMonth).toHaveLength(30);
    expect(inMonth.map((c) => c.day)).toEqual(Array.from({ length: 30 }, (_, i) => i + 1));
    expect(flat[0]).toMatchObject({ iso: '2026-08-31', inMonth: false, day: 31 });
    expect(flat[flat.length - 1]).toMatchObject({ iso: '2026-10-04', inMonth: false, day: 4 });
  });

  it('places API days by ISO date, never consecutively', () => {
    const weeks = buildMonthGrid('2026-09', 1, [day('2026-09-20', [item('x', '2026-09-20')])]);
    const flat = weeks.flat();
    expect(flat.find((c) => c.iso === '2026-09-20')?.items).toHaveLength(1);
    expect(flat.find((c) => c.iso === '2026-09-01')?.items).toHaveLength(0);
    expect(columnOf('2026-09-20', 1)).toBe(6);
  });

  it('drops tax items client-side and the days that only held them', () => {
    const days = dropTax([
      day('2026-09-17', [item('resico', '2026-09-17', 'tax')]),
      day('2026-09-18', [item('resico2', '2026-09-18', 'tax'), item('net', '2026-09-18')]),
    ]);
    expect(days.map((d) => d.date)).toEqual(['2026-09-18']);
    expect(days[0].items.map((i) => i.id)).toEqual(['net']);
  });

  it('handles a 6-week month and a leap February', () => {
    expect(buildMonthGrid('2026-08', 0, [])).toHaveLength(6); // Aug 2026 starts Saturday
    expect(buildMonthGrid('2028-02', 1, []).flat().filter((c) => c.inMonth)).toHaveLength(29);
  });
});
