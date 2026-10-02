/**
 * period.ts: local "now", month math across year
 * boundaries, bounds. TZ is America/Mexico_City (tests/setup.ts).
 */
import { describe, expect, it } from 'vitest';
import { closePeriod, currentPeriod, monthBounds, nextPeriod, periodLabel, previousPeriod, shiftPeriod } from '@/lib/period';

describe('currentPeriod (local time)', () => {
  it('23:30 on 2026-09-12 in Mexico City is 2026-09', () => {
    expect(currentPeriod(new Date('2026-09-12T23:30:00-06:00'))).toBe('2026-09');
  });
  it('a local Sep 30 23:30 stays in September although it is Oct 1 in UTC', () => {
    expect(currentPeriod(new Date('2026-09-30T23:30:00-06:00'))).toBe('2026-09');
    expect(new Date('2026-09-30T23:30:00-06:00').toISOString().slice(0, 7)).toBe('2026-10');
  });
  it('Dec 31 20:00 local is still December although UTC is already January', () => {
    expect(currentPeriod(new Date('2026-12-31T20:00:00-06:00'))).toBe('2026-12');
    expect(new Date('2026-12-31T20:00:00-06:00').toISOString().slice(0, 7)).toBe('2027-01');
  });
});

describe('shiftPeriod', () => {
  it('walks across year boundaries both ways', () => {
    expect(shiftPeriod('2026-01', -1)).toBe('2025-12');
    expect(shiftPeriod('2026-12', 1)).toBe('2027-01');
    expect(shiftPeriod('2026-03', -15)).toBe('2024-12');
    expect(shiftPeriod('2026-03', 0)).toBe('2026-03');
  });
  it('matches the legacy previous/next helpers', () => {
    expect(shiftPeriod('2026-06', -1)).toBe(previousPeriod('2026-06'));
    expect(shiftPeriod('2026-06', 1)).toBe(nextPeriod('2026-06'));
  });
});

describe('monthBounds', () => {
  it('handles February, leap years and 31-day months', () => {
    expect(monthBounds('2026-02')).toEqual({ from: '2026-02-01', to: '2026-02-28' });
    expect(monthBounds('2028-02')).toEqual({ from: '2028-02-01', to: '2028-02-29' });
    expect(monthBounds('2026-12')).toEqual({ from: '2026-12-01', to: '2026-12-31' });
  });
});

describe('periodLabel / closePeriod', () => {
  it('delegates to formatPeriod (table, not Intl)', () => {
    expect(periodLabel('2026-09', 'es')).toBe('sep 2026');
    expect(periodLabel('2026-09', 'en')).toBe('Sep 2026');
  });
  it('closePeriod is untouched: the month that just ended', () => {
    expect(closePeriod(new Date('2026-09-12T12:00:00-06:00'))).toBe('2026-08');
  });
});
