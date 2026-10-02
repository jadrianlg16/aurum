/**
 * The per-area string files, one per part of the app (core, data, home, movimientos, cuentas,
 * money, plan, novice). Each file follows the `i18n-personal.ts` contract (`es` is the key set, `en`
 * must cover it); this index merges them and `../i18n.tsx` spreads the result LAST into `DICTS`.
 *
 * Imported as `./i18n/index` on purpose — `@/lib/i18n` must keep resolving to `i18n.tsx`.
 */
import * as core from './core';
import * as cuentas from './cuentas';
import * as data from './data';
import * as home from './home';
import * as money from './money';
import * as movimientos from './movimientos';
import * as novice from './novice';
import * as plan from './plan';

export const AREA_ES = {
  ...core.es,
  ...data.es,
  ...home.es,
  ...movimientos.es,
  ...cuentas.es,
  ...money.es,
  ...plan.es,
  ...novice.es,
} as const;

export const AREA_EN: Record<keyof typeof AREA_ES, string> = {
  ...core.en,
  ...data.en,
  ...home.en,
  ...movimientos.en,
  ...cuentas.en,
  ...money.en,
  ...plan.en,
  ...novice.en,
};
