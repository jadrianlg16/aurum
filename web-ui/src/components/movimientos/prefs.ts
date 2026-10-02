/**
 * Per-workspace conveniences kept in localStorage (the `aurum.*` registry in design-system.md):
 *
 *   aurum.lastAccount.<ws>  the account the person last saved a movement on (string id)
 *   aurum.catUsage.<ws>     `{[label_id]: n}` — how many times each category was saved
 *
 * Every read and write is wrapped in try/catch: a blocked or full storage must never break the
 * "+ Agregar" dialog, and an unparsable value reads as "nothing stored". Ajustes › "Restablecer
 * preferencias" clears both keys.
 */

export const LAST_ACCOUNT_KEY = (ws: string) => `aurum.lastAccount.${ws}`;
export const CAT_USAGE_KEY = (ws: string) => `aurum.catUsage.${ws}`;

/** How many "Frecuentes" chips the dialog shows. */
export const FREQUENT_LIMIT = 6;

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readLastAccount(ws: string): string | null {
  try {
    const v = storage()?.getItem(LAST_ACCOUNT_KEY(ws));
    return v && v.trim() ? v : null;
  } catch {
    return null;
  }
}

export function writeLastAccount(ws: string, accountId: string): void {
  try {
    if (accountId) storage()?.setItem(LAST_ACCOUNT_KEY(ws), accountId);
  } catch {
    /* storage blocked — the default account rule still works */
  }
}

export type CatUsage = Record<string, number>;

export function readCatUsage(ws: string): CatUsage {
  try {
    const raw = storage()?.getItem(CAT_USAGE_KEY(ws));
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const out: CatUsage = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === 'number' && Number.isFinite(v) && v > 0) out[k] = Math.floor(v);
    }
    return out;
  } catch {
    return {};
  }
}

/** +1 for one category after a successful save. */
export function bumpCatUsage(ws: string, labelId: string): void {
  if (!labelId) return;
  try {
    const usage = readCatUsage(ws);
    usage[labelId] = (usage[labelId] ?? 0) + 1;
    storage()?.setItem(CAT_USAGE_KEY(ws), JSON.stringify(usage));
  } catch {
    /* ignore */
  }
}

/** The most-used ids, highest count first (ties keep insertion order), at most `limit`. */
export function topCategories(usage: CatUsage, limit = FREQUENT_LIMIT): string[] {
  return Object.entries(usage)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id]) => id);
}
