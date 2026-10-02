#!/usr/bin/env node
/**
 * Vocabulary gate.
 *
 * 1. Banned vocabulary: every NON-advanced value of every dictionary (i18n.tsx/3/4/5 and the
 *    per-area files in `src/lib/i18n/`) is matched against the banned regex list. The list and
 *    the advanced-key prefixes are read from the fenced blocks ```banned-regex``` /
 *    ```advanced-prefixes``` in docs/modules/design-system.md; if that file or a block is
 *    missing, the built-in defaults below apply, with a WARN.
 * 2. `closePeriod` must not be imported by the personal pages: app/page.tsx,
 *    movimientos, presupuesto, metas, cuentas, money, empezar.
 *
 * `scripts/vocab-baseline.json` is a ratchet: known legacy hits are listed there
 * (`values`: `file:key` strings; `close_period_imports`: page paths). Listed hits are
 * tolerated, NEW hits fail, and a listed hit that is gone fails until removed — the file only
 * ever shrinks. Exit 1 on any failure.
 *
 *   node scripts/check-vocab.mjs                 # gate
 *   node scripts/check-vocab.mjs --write-baseline # regenerate the ratchet (review the diff!)
 */
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadDictionary } from './check-i18n.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const REPO = path.resolve(ROOT, '..');
const DESIGN_DOC = path.join(REPO, 'docs', 'modules', 'design-system.md');
const BASELINE = path.join(HERE, 'vocab-baseline.json');

/** The built-in defaults (same list as the `banned-regex` block of design-system.md). */
export const DEFAULT_BANNED = [
  '\\b(Assets|Liabilities|Income|Expenses|Equity):',
  '\\bBandeja\\b',
  '\\bAsiento\\b',
  'compromiso',
  '\\bEtiqueta\\b',
  'Espacio de trabajo',
  'Importe',
  'Beneficiario',
  'Confianza \\d+%',
  'RESICO|DIOT|CFDI|\\bISR\\b|\\bIVA\\b|Beancount|Libros|localStorage|Bearer|AURUM_',
  '[a-z]+_[a-z]+',
];

/** Key prefixes whose values only ever render behind "Avanzado" (not scanned). */
export const DEFAULT_ADVANCED_PREFIXES = [
  'tax.', 'taxes.', 'us.', 'ustax.', 'xb.', 'crossborder.', 'biz.', 'business.', 'payroll.', 'invoice.',
  'research.', 'watch.', 'wf.', 'workflow.', 'workflows.', 'reports.', 'report.', 'holdings.', 'scenario.',
  'scenarios.', 'inbox.', 'books.', 'ledger.', 'journal.', 'cfdi.', 'reconcile.', 'docs.', 'documents.',
  'credit.', 'mcp.', 'settings.token', 'settings.mcp', 'settings.llm', 'settings.health', 'settings.label',
  'settings.labels', 'insight.', 'insights.', 'avisos.', 'digest.', 'deadline.tax', 'trust.', 'explain.',
  'rule.', 'rules.', 'statement.', 'sync.', 'vault.', 'posting.', 'txn.postings', 'tools.', 'plan.scenarios',
  'plan.holdings', 'plan.credit', 'org.setup', 'money.setup', 'money.plan', 'creditreport.', 'fx.',
  'workspace.', 'ws.form', 'mode.', 'adv.', 'advanced.',
];

const PERSONAL_PAGES = ['page.tsx', 'movimientos', 'presupuesto', 'metas', 'cuentas', 'money', 'empezar'];

const DICTIONARIES = [
  ['src/lib/i18n.tsx', 'es', 'en'],
  ['src/lib/i18n-business.ts', 'ES3', 'EN3'],
  ['src/lib/i18n-organizer.ts', 'ES4', 'EN4'],
  ['src/lib/i18n-personal.ts', 'ES5', 'EN5'],
  ...readdirSync(path.join(ROOT, 'src', 'lib', 'i18n'))
    .filter((f) => f.endsWith('.ts') && f !== 'index.ts')
    .sort()
    .map((f) => [`src/lib/i18n/${f}`, 'es', 'en']),
];

/* ----------------------------------------------------- design-system.md */

function fencedBlock(md, lang) {
  const re = new RegExp('```' + lang + '\\s*\\n([\\s\\S]*?)```');
  const m = re.exec(md);
  return m ? m[1].split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#')) : null;
}

export function loadRules() {
  if (!existsSync(DESIGN_DOC)) {
    return { banned: DEFAULT_BANNED, advanced: DEFAULT_ADVANCED_PREFIXES, source: 'defaults', warn: `WARN  ${path.relative(REPO, DESIGN_DOC)} not found — using the built-in defaults` };
  }
  const md = readFileSync(DESIGN_DOC, 'utf8');
  const banned = fencedBlock(md, 'banned-regex');
  const advanced = fencedBlock(md, 'advanced-prefixes');
  const warns = [];
  if (!banned) warns.push('WARN  no ```banned-regex``` block in design-system.md — using defaults');
  if (!advanced) warns.push('WARN  no ```advanced-prefixes``` block in design-system.md — using defaults');
  return { banned: banned ?? DEFAULT_BANNED, advanced: advanced ?? DEFAULT_ADVANCED_PREFIXES, source: banned || advanced ? 'design-system.md' : 'defaults', warn: warns.join('\n') };
}

/* ------------------------------------------------------------- scanning */

const isAdvanced = (key, prefixes) => prefixes.some((p) => key.startsWith(p));

/** Placeholders are not words: `{message}` must not trip the snake_case regex. */
const stripPlaceholders = (v) => v.replace(/\{\w+\}/g, ' ');

export function scanDictionaries(dicts, rules) {
  const regexes = rules.banned.map((r) => new RegExp(r));
  const hits = [];
  for (const d of dicts) {
    for (const [side, entries] of [['es', d.es], ['en', d.en]]) {
      for (const e of entries) {
        if (e.value === null || isAdvanced(e.key, rules.advanced)) continue;
        const text = stripPlaceholders(e.value);
        for (const re of regexes) {
          const m = re.exec(text);
          if (m) {
            hits.push({ id: `${d.file}:${side}:${e.key}`, file: d.file, side, key: e.key, match: m[0], rule: re.source });
            break;
          }
        }
      }
    }
  }
  return hits;
}

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  if (statSync(dir).isFile()) return [...out, dir];
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

/** Personal page files that still import `closePeriod` (the target is zero). */
export function closePeriodImports() {
  const files = PERSONAL_PAGES.flatMap((p) => walk(path.join(ROOT, 'src', 'app', p)));
  return files
    .filter((f) => /\bclosePeriod\b/.test(readFileSync(f, 'utf8')))
    .map((f) => path.relative(ROOT, f).replace(/\\/g, '/'))
    .sort();
}

/* ----------------------------------------------------------------- main */

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const rules = loadRules();
  if (rules.warn) console.log(rules.warn);
  const dicts = DICTIONARIES.map(([f, es, en]) => loadDictionary(f, es, en));
  const hits = scanDictionaries(dicts, rules);
  const closeImports = closePeriodImports();

  if (process.argv.includes('--write-baseline')) {
    writeFileSync(
      BASELINE,
      JSON.stringify(
        {
          _comment: 'Ratchet for scripts/check-vocab.mjs: known legacy banned-vocabulary hits and closePeriod imports. Listed entries are tolerated, new ones fail, stale ones fail — this file only shrinks.',
          values: hits.map((h) => h.id).sort(),
          close_period_imports: closeImports,
        },
        null,
        2,
      ) + '\n',
    );
    console.log(`wrote ${path.relative(ROOT, BASELINE)}: ${hits.length} value hit(s), ${closeImports.length} closePeriod import(s)`);
    process.exit(0);
  }

  const baseline = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : { values: [], close_period_imports: [] };
  const tolerated = new Set(baseline.values ?? []);
  const toleratedImports = new Set(baseline.close_period_imports ?? []);
  const problems = [];
  for (const h of hits) if (!tolerated.has(h.id)) problems.push(`FAIL  banned vocabulary: ${h.key} (${h.file} ${h.side}) — "${h.match}" matches /${h.rule}/`);
  const hitIds = new Set(hits.map((h) => h.id));
  for (const id of tolerated) if (!hitIds.has(id)) problems.push(`FAIL  stale baseline entry (no longer a hit — remove it): ${id}`);
  for (const f of closeImports) if (!toleratedImports.has(f)) problems.push(`FAIL  closePeriod imported by a personal page: ${f}`);
  for (const f of toleratedImports) if (!closeImports.includes(f)) problems.push(`FAIL  stale baseline close_period_imports entry (remove it): ${f}`);

  console.log(`rules: ${rules.banned.length} banned regex(es), ${rules.advanced.length} advanced prefix(es) (${rules.source})`);
  console.log(`scanned ${dicts.reduce((n, d) => n + d.es.length + d.en.length, 0)} values in ${dicts.length} files: ${hits.length} hit(s), ${tolerated.size} tolerated by baseline`);
  console.log(`closePeriod imports under personal pages: ${closeImports.length} (${closeImports.join(', ') || '—'}); baseline tolerates ${toleratedImports.size}`);
  for (const p of problems) console.log(p);
  console.log(problems.length ? `\ncheck-vocab: ${problems.length} problem(s)` : '\ncheck-vocab: OK');
  process.exit(problems.length ? 1 : 0);
}
