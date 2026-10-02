/**
 * `groupByDay`: keeps the API order, one group per date, and a
 * display-only subtotal that leaves transfers out and never touches a float.
 */
import { describe, expect, it } from 'vitest';
import type { Entry } from '@/lib/types-personal';
import { groupByDay } from './dayGroups';

const row = (over: Partial<Entry>): Entry => ({
  id: over.id ?? 'e',
  date: '2026-09-12',
  kind: 'expense',
  payee: null,
  note: null,
  amount: { amount: '-250.00', currency: 'MXN' },
  account_id: 'a1',
  account_name: 'Débito',
  to_account_id: null,
  to_account_name: null,
  label_id: null,
  label_name: null,
  splits: [],
  tags: [],
  source: 'manual',
  txn_id: null,
  commitment_id: null,
  attachment: null,
  voided: false,
  editable: true,
  non_editable_reason: null,
  ...over,
});

describe('groupByDay', () => {
  it('groups consecutive rows by date in the order the API returned', () => {
    const groups = groupByDay([
      row({ id: '1', date: '2026-09-12' }),
      row({ id: '2', date: '2026-09-12', amount: { amount: '-0.10', currency: 'MXN' } }),
      row({ id: '3', date: '2026-09-11', kind: 'income', amount: { amount: '1000.00', currency: 'MXN' } }),
    ]);
    expect(groups.map((g) => g.date)).toEqual(['2026-09-12', '2026-09-11']);
    expect(groups[0].rows.map((r) => r.id)).toEqual(['1', '2']);
    expect(groups[0].subtotal).toBe('-250.10');
    expect(groups[1].subtotal).toBe('1000.00');
    expect(groups[1].currency).toBe('MXN');
  });

  it('leaves transfers out of the subtotal (0.00 when the day only has transfers)', () => {
    const groups = groupByDay([
      row({ id: 't', kind: 'transfer', amount: { amount: '-500.00', currency: 'MXN' }, to_account_id: 'a2' }),
      row({ id: 'e', amount: { amount: '-20.00', currency: 'MXN' } }),
      row({ id: 'only', date: '2026-09-10', kind: 'transfer', amount: { amount: '-99.00', currency: 'MXN' } }),
    ]);
    expect(groups[0].subtotal).toBe('-20.00');
    expect(groups[1].subtotal).toBe('0.00');
  });

  it('has no subtotal when a day mixes currencies (never adds USD to MXN)', () => {
    const groups = groupByDay([
      row({ id: 'usd', account_id: 'usd', amount: { amount: '-100.00', currency: 'USD' } }),
      row({ id: 'mxn', amount: { amount: '-500.00', currency: 'MXN' } }),
      // a transfer in another currency does not make the day "mixed": it is not counted anyway
      row({ id: 'single', date: '2026-09-11', amount: { amount: '-40.00', currency: 'USD' } }),
      row({ id: 't', date: '2026-09-11', kind: 'transfer', amount: { amount: '-1.00', currency: 'MXN' }, to_account_id: 'a2' }),
    ]);
    expect(groups[0].subtotal).toBeNull();
    expect(groups[1].subtotal).toBe('-40.00');
    expect(groups[1].currency).toBe('USD');
  });

  it('returns no groups for no rows', () => {
    expect(groupByDay([])).toEqual([]);
  });
});
