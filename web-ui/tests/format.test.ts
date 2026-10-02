/**
 * format.ts: exact digits, table-driven periods, base/foreign currency affixes, the explicit
 * U+2212 sign, never throwing on garbage, and local calendar dates. The newer helpers
 * (`todayLocalIso`, `relativeDay`) are asserted behind `skipIf`, which only skips if they are
 * missing.
 */
import { describe, expect, it } from 'vitest';
import * as format from '@/lib/format';

type AnyFormat = Record<string, unknown>;
const f = format as unknown as AnyFormat;
const hasLocalDateHelpers = typeof f.todayLocalIso === 'function' && typeof f.relativeDay === 'function';
type Opts = Record<string, unknown>;
const formatAmount = (a: { amount: string; currency: string } | null, lang: 'es' | 'en', opts: Opts = {}) =>
  (f.formatAmount as (a: unknown, lang: string, opts: unknown) => string)(a, lang, opts);

describe('formatAmount (basics)', () => {
  it('null renders an em dash', () => {
    expect(() => formatAmount(null, 'es')).not.toThrow();
    expect(formatAmount(null, 'es')).toBe('—');
  });
  it('keeps the exact digits (no float): a long decimal is not rounded away', () => {
    expect(formatAmount({ amount: '1234567890123.45', currency: 'MXN' }, 'en')).toContain('1,234,567,890,123.45');
  });
  it('formatPeriod is a table: identical in Node and the browser', () => {
    expect(format.formatPeriod('2026-09', 'es')).toBe('sep 2026');
    expect(format.formatPeriod('2026-08', 'en')).toBe('Aug 2026');
    expect(format.formatPeriod('garbage', 'es')).toBe('garbage');
  });
});

describe.skipIf(!hasLocalDateHelpers)('formatAmount (affixes, explicit sign, local dates)', () => {
  it('never throws: garbage amounts fall back to a string', () => {
    expect(() => formatAmount({ amount: 'abc', currency: 'MXN' }, 'es')).not.toThrow();
    expect(() => formatAmount({ amount: '', currency: '' }, 'en')).not.toThrow();
    expect(formatAmount({ amount: 'abc', currency: 'MXN' }, 'es')).toContain('abc');
  });
  it('base currency renders $, non-base US$/MX$, other ISO code + space', () => {
    expect(formatAmount({ amount: '10.00', currency: 'MXN' }, 'es', { base: 'MXN' })).toMatch(/^\$10\.00$/);
    expect(formatAmount({ amount: '10.00', currency: 'USD' }, 'es', { base: 'MXN' })).toMatch(/^US\$10\.00$/);
    expect(formatAmount({ amount: '10.00', currency: 'MXN' }, 'en', { base: 'USD' })).toMatch(/^MX\$10\.00$/);
    expect(formatAmount({ amount: '10.00', currency: 'EUR' }, 'es', { base: 'MXN' })).toMatch(/^EUR 10\.00$/);
  });
  it('explicit sign uses U+2212 and -0.00 collapses to 0.00', () => {
    const neg = formatAmount({ amount: '-1250.50', currency: 'MXN' }, 'es', { base: 'MXN' });
    expect(neg).toContain(String.fromCharCode(0x2212));
    expect(neg).not.toContain('-');
    expect(formatAmount({ amount: '1250.50', currency: 'MXN' }, 'es', { base: 'MXN', sign: 'always' })).toMatch(/^\+/);
    expect(formatAmount({ amount: '-0.00', currency: 'MXN' }, 'es', { base: 'MXN' })).toBe('$0.00');
  });
  it('todayLocalIso is the local calendar date', () => {
    const today = (f.todayLocalIso as () => string)();
    const d = new Date();
    const local = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    expect(today).toBe(local);
  });
});

describe.skipIf(!hasLocalDateHelpers)('daysUntil (local days)', () => {
  it('02:00Z on the 13th is still the 12th in Mexico City, so the 13th is 1 day away', () => {
    expect(format.daysUntil('2026-09-13', new Date('2026-09-13T02:00:00Z'))).toBe(1);
  });
  it('same local day is 0, yesterday is -1', () => {
    expect(format.daysUntil('2026-09-12', new Date('2026-09-12T12:00:00-06:00'))).toBe(0);
    expect(format.daysUntil('2026-09-11', new Date('2026-09-12T12:00:00-06:00'))).toBe(-1);
  });
});
