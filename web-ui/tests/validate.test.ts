/** validate.ts: string-only money checks, no Number() anywhere. */
import { describe, expect, it } from 'vitest';
import { decimal, isDecimalString, isoDate, period, splitsMatch, sumDecimals } from '@/lib/validate';

describe('isDecimalString', () => {
  it('accepts wire decimals and rejects everything else', () => {
    expect(isDecimalString('1250.50')).toBe(true);
    expect(isDecimalString('-3')).toBe(true);
    expect(isDecimalString('0.5')).toBe(true);
    expect(isDecimalString('1,250.50')).toBe(false);
    expect(isDecimalString('12.345')).toBe(false);
    expect(isDecimalString('')).toBe(false);
    expect(isDecimalString(1250.5)).toBe(false);
    expect(isDecimalString(null)).toBe(false);
  });
});

describe('sumDecimals / splitsMatch', () => {
  it('sums exactly in centavos', () => {
    expect(sumDecimals(['0.10', '0.20'])).toBe('0.30');
    expect(sumDecimals(['1000000000.99', '0.01'])).toBe('1000000001.00');
    expect(sumDecimals(['-5', '2.5'])).toBe('-2.50');
  });
  it('splitsMatch compares sign-insensitively and rejects bad input', () => {
    expect(splitsMatch('100.00', ['60', '40.00'])).toBe(true);
    expect(splitsMatch('-100.00', ['60', '40'])).toBe(true);
    expect(splitsMatch('100.00', ['60', '39.99'])).toBe(false);
    expect(splitsMatch('100.00', ['60', 'abc'])).toBe(false);
    expect(splitsMatch('abc', ['1'])).toBe(false);
    expect(splitsMatch('0', [])).toBe(true);
  });
});

describe('legacy validators keep their keys', () => {
  it('decimal / isoDate / period', () => {
    expect(decimal('12.34')).toBeNull();
    expect(decimal('0', { positive: true })).toBe('valid.decimal_positive');
    expect(isoDate('2026-02-30')).toBe('valid.date');
    expect(isoDate('2026-02-28')).toBeNull();
    expect(period('2026-13')).toBe('valid.period');
  });
});
