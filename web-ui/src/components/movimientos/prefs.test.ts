/**
 * localStorage conveniences of the "+ Agregar" dialog:
 * `aurum.lastAccount.<ws>` and `aurum.catUsage.<ws>`, read defensively.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { bumpCatUsage, CAT_USAGE_KEY, LAST_ACCOUNT_KEY, readCatUsage, readLastAccount, topCategories, writeLastAccount } from './prefs';

const WS = 'ws-test';

beforeEach(() => {
  localStorage.clear();
});

describe('last account', () => {
  it('round-trips per workspace and ignores blanks', () => {
    expect(readLastAccount(WS)).toBeNull();
    writeLastAccount(WS, 'acct-1');
    expect(localStorage.getItem(LAST_ACCOUNT_KEY(WS))).toBe('acct-1');
    expect(readLastAccount(WS)).toBe('acct-1');
    expect(readLastAccount('other')).toBeNull();
    writeLastAccount(WS, '');
    expect(readLastAccount(WS)).toBe('acct-1');
  });
});

describe('category usage', () => {
  it('counts +1 per save and orders the most used first', () => {
    bumpCatUsage(WS, 'super');
    bumpCatUsage(WS, 'comida');
    bumpCatUsage(WS, 'comida');
    expect(readCatUsage(WS)).toEqual({ super: 1, comida: 2 });
    expect(topCategories(readCatUsage(WS))).toEqual(['comida', 'super']);
    expect(topCategories({ a: 5, b: 4, c: 3, d: 2, e: 1, f: 1, g: 1 })).toHaveLength(6);
  });

  it('treats garbage as nothing stored', () => {
    localStorage.setItem(CAT_USAGE_KEY(WS), 'not json');
    expect(readCatUsage(WS)).toEqual({});
    localStorage.setItem(CAT_USAGE_KEY(WS), JSON.stringify(['a']));
    expect(readCatUsage(WS)).toEqual({});
    localStorage.setItem(CAT_USAGE_KEY(WS), JSON.stringify({ ok: 2, bad: 'x', neg: -1 }));
    expect(readCatUsage(WS)).toEqual({ ok: 2 });
  });
});
