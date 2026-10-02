/**
 * `/cuentas/` pure helpers: per-currency 'Tienes' / 'Debes' /
 * 'Neto' never blend currencies, owed rows count from the positive `balance`, the base currency
 * sorts first, and the card usage bar is owed/limit as a whole percent.
 */
import { describe, expect, it } from 'vitest';
import type { PfAccount } from '@/lib/types-personal';
import { usagePercent } from './AccountCard';
import { GROUPS, currencyStats } from './stats';

const row = (over: Partial<PfAccount>): PfAccount =>
  ({
    id: over.id ?? over.name ?? 'x',
    name: over.name ?? 'x',
    type: over.type ?? 'checking',
    currency: over.currency ?? 'MXN',
    institution: null,
    balance: over.balance ?? { amount: '0.00', currency: over.currency ?? 'MXN' },
    balance_signed: over.balance_signed ?? over.balance ?? { amount: '0.00', currency: over.currency ?? 'MXN' },
    owed: over.owed ?? false,
    archived: over.archived ?? false,
    credit_limit: over.credit_limit ?? null,
    cut_day: null,
    due_day: null,
    apr: null,
    apr_percent: null,
    loan_months: null,
    loan_principal: null,
    opening_balance: null,
    opening_date: null,
    account: '',
  }) as unknown as PfAccount;

describe('currencyStats', () => {
  it('sums per currency, base first, and never adds MXN to USD', () => {
    const rows = [
      row({ name: 'Débito', balance: { amount: '1000.00', currency: 'MXN' } }),
      row({ name: 'Dólares', type: 'savings', currency: 'USD', balance: { amount: '100.00', currency: 'USD' } }),
      row({
        name: 'Nu',
        type: 'credit_card',
        owed: true,
        balance: { amount: '2610.00', currency: 'MXN' },
        balance_signed: { amount: '-2610.00', currency: 'MXN' },
      }),
    ];
    const stats = currencyStats(rows, 'MXN');
    expect(stats.map((s) => s.currency)).toEqual(['MXN', 'USD']);
    expect(stats[0]).toEqual({ currency: 'MXN', have: '1000.00', owe: '2610.00', net: '-1610.00' });
    expect(stats[1]).toEqual({ currency: 'USD', have: '100.00', owe: '0.00', net: '100.00' });
    expect(JSON.stringify(stats)).not.toContain('1100.00');
  });

  it('puts a non-MXN base first and sorts the rest alphabetically', () => {
    const rows = [
      row({ name: 'a', currency: 'MXN', balance: { amount: '1.00', currency: 'MXN' } }),
      row({ name: 'b', currency: 'EUR', balance: { amount: '1.00', currency: 'EUR' } }),
      row({ name: 'c', currency: 'USD', balance: { amount: '1.00', currency: 'USD' } }),
    ];
    expect(currencyStats(rows, 'USD').map((s) => s.currency)).toEqual(['USD', 'EUR', 'MXN']);
  });

  it('is empty with no rows', () => {
    expect(currencyStats([], 'MXN')).toEqual([]);
  });
});

describe('GROUPS', () => {
  it('covers every account type exactly once', () => {
    const all = GROUPS.flatMap((g) => g.types).sort();
    expect(all).toEqual(['cash', 'checking', 'credit_card', 'investment', 'loan', 'other', 'savings']);
  });
});

describe('usagePercent', () => {
  it('is owed over limit, clamped, and 0 without a limit', () => {
    expect(usagePercent({ amount: '2610.00', currency: 'MXN' }, { amount: '30000.00', currency: 'MXN' })).toBe(9);
    expect(usagePercent({ amount: '45000.00', currency: 'MXN' }, { amount: '30000.00', currency: 'MXN' })).toBe(100);
    expect(usagePercent({ amount: '10.00', currency: 'MXN' }, null)).toBe(0);
    expect(usagePercent({ amount: '10.00', currency: 'MXN' }, { amount: '0.00', currency: 'MXN' })).toBe(0);
  });
});
