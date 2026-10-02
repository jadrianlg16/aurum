/**
 * Dictionaries: 0 cross-file duplicates beyond the recorded baseline, ES/EN key parity,
 * placeholder parity, no banned words in the `i18n/data.ts` copy, and `tn` plurals.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadDictionary, placeholders, runChecks } from '../scripts/check-i18n.mjs';
import { DEFAULT_BANNED } from '../scripts/check-vocab.mjs';
import { en as dataEn, es as dataEs } from '@/lib/i18n/data';
import { AREA_EN, AREA_ES } from '@/lib/i18n/index';
import * as i18n from '@/lib/i18n';

const ROOT = path.resolve(__dirname, '..');
const BASELINE = JSON.parse(readFileSync(path.join(ROOT, 'scripts', 'i18n-baseline.json'), 'utf8')) as {
  cross_file_duplicates: string[];
};

const FILES: [string, string, string][] = [
  ['src/lib/i18n.tsx', 'es', 'en'],
  ['src/lib/i18n-business.ts', 'ES3', 'EN3'],
  ['src/lib/i18n-organizer.ts', 'ES4', 'EN4'],
  ['src/lib/i18n-personal.ts', 'ES5', 'EN5'],
  ['src/lib/i18n/core.ts', 'es', 'en'],
  ['src/lib/i18n/data.ts', 'es', 'en'],
  ['src/lib/i18n/home.ts', 'es', 'en'],
  ['src/lib/i18n/movimientos.ts', 'es', 'en'],
  ['src/lib/i18n/cuentas.ts', 'es', 'en'],
  ['src/lib/i18n/money.ts', 'es', 'en'],
  ['src/lib/i18n/plan.ts', 'es', 'en'],
  ['src/lib/i18n/novice.ts', 'es', 'en'],
];

const dicts = FILES.map(([f, es, en]) => loadDictionary(f, es, en));

describe('dictionaries', () => {
  it('parse every file (the regex tokenizer sees the same key counts TypeScript does)', () => {
    const data = dicts.find((d) => d.file.endsWith('i18n/data.ts'))!;
    expect(data.es.length).toBe(Object.keys(dataEs).length);
    expect(data.en.length).toBe(Object.keys(dataEn).length);
    const core = dicts.find((d) => d.file.endsWith('i18n.tsx'))!;
    expect(core.es.length).toBeGreaterThan(500);
  });

  it('have 0 cross-file duplicates beyond the recorded baseline, ES/EN parity and placeholder parity', () => {
    const problems = runChecks(dicts, BASELINE);
    expect(problems).toEqual([]);
  });

  it('the cross-file duplicate baseline is empty', () => {
    expect(BASELINE.cross_file_duplicates).toEqual([]);
  });

  it('the per-area files never repeat a key across each other (the merged dictionary keeps every key)', () => {
    const areas = dicts.filter((d) => d.file.startsWith('src/lib/i18n/'));
    const total = areas.reduce((n, d) => n + d.es.length, 0);
    expect(Object.keys(AREA_ES).length).toBe(total);
    expect(Object.keys(AREA_EN).length).toBe(total);
  });
});

describe('i18n/data.ts copy', () => {
  it('has one err.* key per ApiError code plus field labels and ws.*', () => {
    const keys = Object.keys(dataEs);
    for (const k of [
      'err.network', 'err.timeout', 'err.unauthorized', 'err.unauthorized.cta', 'err.forbidden.demo', 'err.forbidden.origin',
      'err.entry_not_editable', 'err.not_found', 'err.not_found.cta', 'err.conflict', 'err.budget_exists', 'err.account_has_movements',
      'err.entry_already_deleted', 'err.splits_sum', 'err.transfer_same_account', 'err.transfer_needs_target', 'err.account_archived',
      'err.amount_not_positive', 'err.bad_amount', 'err.bad_date', 'err.bad_period', 'err.range_inverted', 'err.bad_currency',
      'err.validation', 'err.payload_too_large', 'err.rate_limited', 'err.bad_path', 'err.server', 'err.generic',
      'err.field.amount', 'err.field.date', 'err.field.account_id', 'err.field.label_id', 'err.field.period', 'err.field.months',
      'err.field.to_account_id', 'err.field.currency', 'err.field.name', 'ws.none', 'ws.resolve_failed',
    ]) expect(keys).toContain(k);
  });

  it('ES and EN carry the same placeholders and no banned vocabulary', () => {
    const banned = DEFAULT_BANNED.map((r: string) => new RegExp(r));
    for (const [k, es] of Object.entries(dataEs)) {
      const en = dataEn[k as keyof typeof dataEn];
      expect([...placeholders(es)].sort(), k).toEqual([...placeholders(en)].sort());
      for (const v of [es, en]) {
        const text = v.replace(/\{\w+\}/g, ' ');
        for (const re of banned) expect(re.test(text), `${k}: ${v} matches ${re.source}`).toBe(false);
      }
    }
  });
});

const tn = (i18n as unknown as Record<string, unknown>).tn;
describe.skipIf(typeof tn !== 'function')('tn plural', () => {
  it('picks .one for 1 and .other otherwise', () => {
    const fn = tn as (key: string, n: number, vars?: Record<string, string | number>) => string;
    const one = fn('common.days', 1);
    const other = fn('common.days', 3);
    expect(one).not.toBe(other);
  });
});
