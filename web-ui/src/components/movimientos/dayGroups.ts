/**
 * Group a page of movements by day, keeping the order the API returned (date desc, id desc).
 * The per-day subtotal is DISPLAY ONLY (sr-only "Total del día"): signed sum of the day's
 * expense/income rows in centavos through `sumDecimals`; transfers are left out because they
 * move money between the person's own accounts. Accounts carry their own currency
 * (`PfAccount.currency`), so a day whose counted rows mix currencies has NO subtotal (`null`)
 * rather than a figure that adds USD to MXN — the same reason the API's own totals skip
 * non-base rows. Page totals (Entró/Salió/Neto) never come from here — they are the API's
 * `totals`.
 */
import type { Entry } from '@/lib/types-personal';
import { sumDecimals } from '@/lib/validate';

export interface DayGroupData {
  /** ISO date shared by every row of the group. */
  date: string;
  rows: Entry[];
  /**
   * Signed decimal string, e.g. `-1250.00`; `0.00` when the day only has transfers; `null`
   * when the day's expense/income rows are in more than one currency (nothing to add up).
   */
  subtotal: string | null;
  /** Currency of the subtotal (the counted rows' single currency), else of the first row. */
  currency: string;
}

export function groupByDay(rows: Entry[]): DayGroupData[] {
  const out: DayGroupData[] = [];
  const byDate = new Map<string, DayGroupData>();
  for (const row of rows) {
    let g = byDate.get(row.date);
    if (!g) {
      g = { date: row.date, rows: [], subtotal: '0.00', currency: row.amount.currency };
      byDate.set(row.date, g);
      out.push(g);
    }
    g.rows.push(row);
  }
  for (const g of out) {
    const counted = g.rows.filter((r) => r.kind !== 'transfer');
    const currencies = new Set(counted.map((r) => r.amount.currency.toUpperCase()));
    if (currencies.size > 1) {
      g.subtotal = null;
      continue;
    }
    g.subtotal = sumDecimals(counted.map((r) => r.amount.amount));
    g.currency = counted[0]?.amount.currency ?? g.currency;
  }
  return out;
}
