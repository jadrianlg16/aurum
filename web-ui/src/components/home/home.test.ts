/**
 * Pure helpers behind Inicio and Empezar: display sign flips (never a parse),
 * local calendar math, the Próximos pagos row filter, the one allowed client-side
 * sum (liquid balance) and the `?step=` fallback (first step not done).
 */
import { describe, expect, it } from 'vitest';
import type { CalendarItem, OrganizerCalendar } from '@/lib/types-organizer';
import type { PfAccount } from '@/lib/types-personal';
import type { Workspace } from '@/lib/types';
import { liquidBalance } from '@/components/onboarding/DoneScreen';
import { firstNotDone } from '@/components/onboarding/shared';
import { pickDemoWorkspace } from './StartHere';
import { upcomingRows } from './UpcomingPayments';
import { addDaysIso, negate, pctNumber } from './shared';

const item = (over: Partial<CalendarItem>): CalendarItem =>
  ({
    kind: 'commitment',
    date: '2026-09-20',
    id: 'cmt-1',
    name: 'Netflix',
    amount: { amount: '219.00', currency: 'MXN' },
    status: 'upcoming',
    txn_id: null,
    commitment_kind: 'subscription',
    account_id: null,
    account_name: null,
    entry_id: null,
    ...over,
  }) as CalendarItem;

const calendar = (items: CalendarItem[]): OrganizerCalendar =>
  ({ from: '2026-09-19', to: '2026-09-26', days: [{ date: '2026-09-20', items }] }) as unknown as OrganizerCalendar;

describe('negate (display sign flip, no parsing)', () => {
  it('flips positive → negative and back, leaves zero unsigned', () => {
    expect(negate('300.00')).toBe('-300.00');
    expect(negate('-300.00')).toBe('300.00');
    expect(negate('+12.50')).toBe('-12.50');
    expect(negate('0.00')).toBe('0.00');
    expect(negate('-0')).toBe('0');
    expect(negate('')).toBe('');
  });
});

describe('addDaysIso (local)', () => {
  it('crosses month and year ends without UTC drift', () => {
    expect(addDaysIso('2026-09-19', 7)).toBe('2026-09-26');
    expect(addDaysIso('2026-09-28', 7)).toBe('2026-10-05');
    expect(addDaysIso('2026-12-30', 7)).toBe('2027-01-06');
    expect(addDaysIso('not-a-date', 7)).toBe('not-a-date');
  });
});

describe('pctNumber', () => {
  it('reads a percent from a number or a decimal string, never money', () => {
    expect(pctNumber(42)).toBe(42);
    expect(pctNumber('87.5')).toBe(87.5);
    expect(pctNumber(null)).toBe(0);
    expect(pctNumber('x')).toBe(0);
  });
});

describe('upcomingRows', () => {
  it('keeps due/upcoming/missed, drops paid/skipped and tax, preserves order', () => {
    const rows = upcomingRows(
      calendar([
        item({ id: 'a', status: 'due' }),
        item({ id: 'b', status: 'paid' }),
        item({ id: 'c', status: 'missed' }),
        item({ id: 'd', kind: 'tax', status: 'due' }),
        item({ id: 'e', status: 'skipped' }),
        item({ id: 'f', kind: 'income', status: 'upcoming', commitment_kind: 'income' }),
      ]),
    );
    expect(rows.map((r) => r.id)).toEqual(['a', 'c', 'f']);
    expect(upcomingRows(null)).toEqual([]);
  });
});

describe('liquidBalance (the one allowed client-side sum)', () => {
  const acct = (over: Partial<PfAccount>): PfAccount =>
    ({ id: 'x', name: 'x', type: 'checking', currency: 'MXN', archived: false, balance_signed: { amount: '0.00', currency: 'MXN' }, ...over }) as PfAccount;
  it('sums cash/checking/savings in the base currency, skips archived, cards and other currencies', () => {
    const rows = [
      acct({ id: 'a', type: 'checking', balance_signed: { amount: '10000.00', currency: 'MXN' } }),
      acct({ id: 'b', type: 'cash', balance_signed: { amount: '250.50', currency: 'MXN' } }),
      acct({ id: 'c', type: 'savings', balance_signed: { amount: '-0.50', currency: 'MXN' } }),
      acct({ id: 'd', type: 'credit_card', balance_signed: { amount: '-4000.00', currency: 'MXN' } }),
      acct({ id: 'e', type: 'checking', archived: true, balance_signed: { amount: '999.00', currency: 'MXN' } }),
      acct({ id: 'f', type: 'checking', currency: 'USD', balance_signed: { amount: '100.00', currency: 'USD' } }),
    ];
    expect(liquidBalance(rows, 'MXN')).toBe('10250.00');
    expect(liquidBalance([], 'MXN')).toBe('0.00');
  });
});

describe('firstNotDone (?step= fallback)', () => {
  it('returns the first onboarding step not done, else the done screen', () => {
    expect(firstNotDone(undefined)).toBe('accounts');
    expect(
      firstNotDone([
        { id: 'accounts', done: true, count: 1 },
        { id: 'income', done: false, count: 0 },
        { id: 'recurring', done: false, count: 0 },
        { id: 'first_entries', done: false, count: 0 },
      ]),
    ).toBe('income');
    expect(
      firstNotDone([
        { id: 'accounts', done: true },
        { id: 'income', done: true },
        { id: 'recurring', done: true },
        { id: 'first_entries', done: true },
      ]),
    ).toBe('done');
  });
});

describe('pickDemoWorkspace (empty-home secondary action)', () => {
  const w = (over: Partial<Workspace>): Workspace =>
    ({ id: 'x', name: 'x', kind: 'personal', jurisdictions: ['MX'], base_currency: 'MXN', language: 'es', profile: {}, created_at: '', ...over }) as Workspace;
  it("prefers 'demo-personal', else the first listed personal demo, else none", () => {
    expect(pickDemoWorkspace([w({ id: 'a' }), w({ id: 'demo-mx', profile: { demo: true } }), w({ id: 'demo-personal' })])?.id).toBe('demo-personal');
    expect(pickDemoWorkspace([w({ id: 'mock-personal' }), w({ id: 'demo-mx', profile: { demo: true } })])?.id).toBe('demo-mx');
    expect(pickDemoWorkspace([w({ id: 'mock-personal' }), w({ id: 'demo-us', kind: 'business', profile: { demo: true } })])).toBeNull();
    expect(pickDemoWorkspace([w({ id: 'hidden-demo', profile: { demo: true }, hidden: true })])).toBeNull();
    expect(pickDemoWorkspace([])).toBeNull();
  });
});
