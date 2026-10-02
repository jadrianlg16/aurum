/**
 * The advanced catalog (`lib/advanced.ts`) that feeds both the rail's Avanzado group and the
 * `/avanzado/` page: one entry per route, every entry explained in both languages, every group
 * titled, and Negocio only for a business workspace.
 */
import { describe, expect, it } from 'vitest';
import { ADVANCED_GROUPS, ADVANCED_ITEMS, advancedItemsFor } from '@/lib/advanced';
import { translate, type MsgKey } from '@/lib/i18n';

describe('advanced catalog', () => {
  it('lists each route once and puts every route in a known group', () => {
    const hrefs = ADVANCED_ITEMS.map((n) => n.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const n of ADVANCED_ITEMS) expect(ADVANCED_GROUPS).toContain(n.group);
    for (const g of ADVANCED_GROUPS) expect(ADVANCED_ITEMS.some((n) => n.group === g)).toBe(true);
  });

  it('explains every screen and titles every group in es and en', () => {
    const keys: MsgKey[] = [
      ...ADVANCED_ITEMS.flatMap((n) => [n.key, n.desc]),
      ...ADVANCED_GROUPS.map((g) => `adv.hub.group.${g}` as MsgKey),
      'adv.hub.all',
      'adv.hub.sub',
    ];
    for (const lang of ['es', 'en'] as const) {
      for (const k of keys) {
        const text = translate(lang, k);
        expect(text, `${lang}:${k}`).toBeTruthy();
        expect(text, `${lang}:${k}`).not.toBe(k);
      }
    }
  });

  it('shows Negocio only to a business workspace', () => {
    expect(advancedItemsFor('personal').some((n) => n.href === '/business')).toBe(false);
    expect(advancedItemsFor(undefined).some((n) => n.href === '/business')).toBe(false);
    expect(advancedItemsFor('business').some((n) => n.href === '/business')).toBe(true);
    expect(advancedItemsFor('personal')).toHaveLength(ADVANCED_ITEMS.length - 1);
  });
});
