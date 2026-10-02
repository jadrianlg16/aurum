/**
 * Pure helpers for `/cuentas/`: the type → group table and the
 * per-currency 'Tienes' / 'Debes' / 'Neto' figures. `sumDecimals` works in integer centavos —
 * the one client-side sum this screen makes — and currencies are never added together.
 */
import type { PfAccount, PfAccountType } from '@/lib/types-personal';
import { sumDecimals } from '@/lib/validate';

export type GroupKey = 'cash' | 'cards' | 'loans' | 'invest' | 'other';

export const GROUPS: { key: GroupKey; types: PfAccountType[] }[] = [
  { key: 'cash', types: ['checking', 'savings', 'cash'] },
  { key: 'cards', types: ['credit_card'] },
  { key: 'loans', types: ['loan'] },
  { key: 'invest', types: ['investment'] },
  { key: 'other', types: ['other'] },
];

export interface CurrencyStats {
  currency: string;
  have: string;
  owe: string;
  net: string;
}

/** Per-currency totals over the active rows; base currency first, then alphabetical. */
export function currencyStats(rows: PfAccount[], base: string): CurrencyStats[] {
  const byCur = new Map<string, PfAccount[]>();
  for (const a of rows) {
    const c = (a.currency ?? base).toUpperCase();
    (byCur.get(c) ?? byCur.set(c, []).get(c)!).push(a);
  }
  const order = [...byCur.keys()].sort((x, y) => (x === base ? -1 : y === base ? 1 : x.localeCompare(y)));
  return order.map((currency) => {
    const list = byCur.get(currency) ?? [];
    const have = sumDecimals(list.filter((a) => !a.owed).map((a) => a.balance_signed?.amount ?? a.balance?.amount ?? '0'));
    const owe = sumDecimals(list.filter((a) => a.owed).map((a) => a.balance?.amount ?? '0'));
    const net = sumDecimals([have, `-${owe}`]);
    return { currency, have, owe, net };
  });
}
