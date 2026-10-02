/**
 * Ingresos pure helpers: the history badge is decided by the money
 * first and both status vocabularies (live `upcoming|due|paid|missed|skipped`, mock
 * `received|late|pending|missed`) land somewhere; weekday names are Monday-first (0 = Monday,
 * the organizer convention) so 'viernes' is index 4.
 */
import { describe, expect, it } from 'vitest';
import { weekdayNames } from './StreamForm';
import { historyStatus } from './StreamHistory';

const m = (amount: string) => ({ amount, currency: 'MXN' });

describe('historyStatus', () => {
  it('reads the money before the status word', () => {
    expect(historyStatus({ expected: m('100.00'), received: m('100.00'), status: 'paid' })).toBe('received');
    expect(historyStatus({ expected: m('100.00'), received: m('120.00'), status: 'paid' })).toBe('received');
    expect(historyStatus({ expected: m('100.00'), received: m('80.00'), status: 'paid' })).toBe('less');
    expect(historyStatus({ expected: null, received: m('80.00'), status: 'received' })).toBe('received');
  });

  it('maps both the live and the mock status vocabularies', () => {
    expect(historyStatus({ expected: m('100.00'), received: null, status: 'missed' })).toBe('missed');
    expect(historyStatus({ expected: m('100.00'), received: null, status: 'skipped' })).toBe('skipped');
    for (const s of ['upcoming', 'due', 'pending', 'late', null, undefined]) {
      expect(historyStatus({ expected: m('100.00'), received: null, status: s })).toBe('pending');
    }
  });
});

describe('weekdayNames', () => {
  it('is Monday-first in both languages, viernes/Friday at 4', () => {
    const es = weekdayNames('es');
    const en = weekdayNames('en');
    expect(es).toHaveLength(7);
    expect(es[0].toLowerCase()).toBe('lunes');
    expect(es[4].toLowerCase()).toBe('viernes');
    expect(es[6].toLowerCase()).toBe('domingo');
    expect(en[0]).toBe('Monday');
    expect(en[4]).toBe('Friday');
  });
});
