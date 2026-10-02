#!/usr/bin/env node
/**
 * i18n dictionary gate.
 *
 * Parses the TS dictionaries by tokenizing (Node 20 cannot import TS): `src/lib/i18n.tsx`
 * (`const es = {…} as const` and `const en = {…}`), `i18n-business/4/5.ts` (`ES3/EN3` …) and every
 * `src/lib/i18n/*.ts` except `index.ts` (`es`/`en`). Values may be single/double-quoted strings, template
 * literals (backticks, possibly multi-line) or `'a' + 'b'` concatenations.
 *
 * Fails (exit 1) on: a key repeated inside one object; a key present in two ES objects
 * (cross-file duplicate — the later spread silently wins); ES/EN key mismatch in one file;
 * `{placeholder}` sets that differ between ES and EN. Prints the unused-key report (non-fatal).
 *
 * `scripts/i18n-baseline.json` is a ratchet for known cross-file duplicates (it is empty now).
 * Listed ones are tolerated; new ones fail; a listed one that disappeared fails too, so the
 * file only ever shrinks.
 *
 *   node scripts/check-i18n.mjs            # gate
 *   node scripts/check-i18n.mjs --json     # machine-readable
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SRC = path.join(ROOT, 'src');
const BASELINE = path.join(HERE, 'i18n-baseline.json');

/** [file, esObject, enObject] */
const DICTIONARIES = [
  ['src/lib/i18n.tsx', 'es', 'en'],
  ['src/lib/i18n-business.ts', 'ES3', 'EN3'],
  ['src/lib/i18n-organizer.ts', 'ES4', 'EN4'],
  ['src/lib/i18n-personal.ts', 'ES5', 'EN5'],
  ...readdirSync(path.join(SRC, 'lib', 'i18n'))
    .filter((f) => f.endsWith('.ts') && f !== 'index.ts')
    .sort()
    .map((f) => [`src/lib/i18n/${f}`, 'es', 'en']),
];

/* ------------------------------------------------------------- tokenizer */

/** Index of the `{` that opens `const <name>[: type] = {`. */
function findObjectStart(src, name) {
  const re = new RegExp(`(?:^|\\n)\\s*(?:export\\s+)?const\\s+${name}\\b[^=]*=\\s*\\{`, 'm');
  const m = re.exec(src);
  if (!m) return -1;
  return m.index + m[0].length - 1;
}

/** Read one JS string literal starting at `i` (quote char at src[i]); returns [value, next]. */
function readString(src, i) {
  const q = src[i];
  let out = '';
  let j = i + 1;
  while (j < src.length) {
    const c = src[j];
    if (c === '\\') {
      const n = src[j + 1];
      if (n === 'n') out += '\n';
      else if (n === 't') out += '\t';
      else if (n === 'u' && /^[0-9a-f]{4}$/i.test(src.slice(j + 2, j + 6))) {
        out += String.fromCharCode(parseInt(src.slice(j + 2, j + 6), 16));
        j += 6;
        continue;
      } else out += n;
      j += 2;
      continue;
    }
    if (c === q) return [out, j + 1];
    if (q === '`' && c === '$' && src[j + 1] === '{') {
      // Keep `${expr}` verbatim — it is a placeholder-like thing, reported as is.
      const close = src.indexOf('}', j);
      out += src.slice(j, close + 1);
      j = close + 1;
      continue;
    }
    out += c;
    j += 1;
  }
  throw new Error('unterminated string');
}

function skipWs(src, i) {
  for (;;) {
    while (i < src.length && /\s/.test(src[i])) i += 1;
    if (src.startsWith('//', i)) {
      i = src.indexOf('\n', i);
      if (i < 0) return src.length;
      continue;
    }
    if (src.startsWith('/*', i)) {
      i = src.indexOf('*/', i) + 2;
      continue;
    }
    return i;
  }
}

/**
 * Parse the flat object at `open` into `[{key, value, line}]` (every occurrence — duplicates
 * are kept so they can be reported). Nested objects / arrays are skipped as opaque values.
 */
function parseObject(src, open) {
  const entries = [];
  let i = open + 1;
  const lineOf = (pos) => src.slice(0, pos).split('\n').length;
  for (;;) {
    i = skipWs(src, i);
    if (src[i] === '}') return { entries, end: i };
    if (src.startsWith('...', i)) {
      // spread — skip to the next comma at depth 0
      while (i < src.length && src[i] !== ',' && src[i] !== '}') i += 1;
      if (src[i] === ',') i += 1;
      continue;
    }
    let key;
    const keyPos = i;
    if (src[i] === "'" || src[i] === '"') [key, i] = readString(src, i);
    else {
      const m = /^[A-Za-z_$][\w$]*/.exec(src.slice(i));
      if (!m) throw new Error(`bad key at line ${lineOf(i)}`);
      key = m[0];
      i += key.length;
    }
    i = skipWs(src, i);
    if (src[i] !== ':') throw new Error(`expected ':' after ${key} at line ${lineOf(i)}`);
    i = skipWs(src, i + 1);
    let value = '';
    let opaque = false;
    for (;;) {
      if (src[i] === "'" || src[i] === '"' || src[i] === '`') {
        const [v, next] = readString(src, i);
        value += v;
        i = skipWs(src, next);
        if (src[i] === '+') {
          i = skipWs(src, i + 1);
          continue;
        }
        break;
      }
      // anything else: skip a balanced expression up to the next top-level comma / brace
      opaque = true;
      let depth = 0;
      while (i < src.length) {
        const c = src[i];
        if (c === "'" || c === '"' || c === '`') {
          [, i] = readString(src, i);
          continue;
        }
        if (c === '{' || c === '[' || c === '(') depth += 1;
        else if (c === '}' || c === ']' || c === ')') {
          if (depth === 0) break;
          depth -= 1;
        } else if (c === ',' && depth === 0) break;
        i += 1;
      }
      break;
    }
    entries.push({ key, value: opaque ? null : value, line: lineOf(keyPos) });
    i = skipWs(src, i);
    if (src[i] === ',') i += 1;
  }
}

export function loadDictionary(file, esName, enName) {
  const src = readFileSync(path.join(ROOT, file), 'utf8').replace(/\r\n?/g, '\n');
  const read = (name) => {
    const open = findObjectStart(src, name);
    if (open < 0) throw new Error(`${file}: object ${name} not found`);
    return parseObject(src, open).entries;
  };
  return { file, es: read(esName), en: read(enName) };
}

export const placeholders = (value) =>
  new Set([...(value ?? '').matchAll(/\{(\w+)\}/g)].map((m) => m[1]));

/* ----------------------------------------------------------------- checks */

export function runChecks(dicts, baseline) {
  const problems = [];
  const seenAcross = new Map(); // key -> file

  for (const d of dicts) {
    for (const [side, entries] of [['es', d.es], ['en', d.en]]) {
      const counts = new Map();
      for (const e of entries) counts.set(e.key, (counts.get(e.key) ?? 0) + 1);
      for (const [k, n] of counts) if (n > 1) problems.push({ kind: 'in-file duplicate', file: d.file, side, key: k, detail: `${n}×` });
    }
    const esKeys = new Set(d.es.map((e) => e.key));
    const enKeys = new Set(d.en.map((e) => e.key));
    for (const k of esKeys) if (!enKeys.has(k)) problems.push({ kind: 'missing in en', file: d.file, key: k });
    for (const k of enKeys) if (!esKeys.has(k)) problems.push({ kind: 'missing in es', file: d.file, key: k });
    const enByKey = new Map(d.en.map((e) => [e.key, e.value]));
    for (const e of d.es) {
      if (e.value === null || !enByKey.has(e.key) || enByKey.get(e.key) === null) continue;
      const a = [...placeholders(e.value)].sort().join(',');
      const b = [...placeholders(enByKey.get(e.key))].sort().join(',');
      if (a !== b) problems.push({ kind: 'placeholder mismatch', file: d.file, key: e.key, detail: `es {${a}} vs en {${b}}` });
    }
    for (const k of esKeys) {
      if (seenAcross.has(k)) {
        const pair = `${k}`;
        if (baseline.cross_file_duplicates.includes(pair)) continue;
        problems.push({ kind: 'cross-file duplicate', file: d.file, key: k, detail: `also in ${seenAcross.get(k)}` });
      } else seenAcross.set(k, d.file);
    }
  }
  // ratchet: a baseline entry that no longer duplicates must be removed from the file
  const dupNow = new Set();
  const first = new Map();
  for (const d of dicts) for (const e of d.es) {
    if (first.has(e.key) && first.get(e.key) !== d.file) dupNow.add(e.key);
    if (!first.has(e.key)) first.set(e.key, d.file);
  }
  for (const k of baseline.cross_file_duplicates) {
    if (!dupNow.has(k)) problems.push({ kind: 'stale baseline entry', file: 'scripts/i18n-baseline.json', key: k, detail: 'no longer duplicated — remove it' });
  }
  return problems;
}

/* ------------------------------------------------------------ unused keys */

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|mjs)$/.test(name)) out.push(p);
  }
  return out;
}

export function unusedKeys(dicts) {
  const dictFiles = new Set(dicts.map((d) => path.join(ROOT, d.file)));
  const code = walk(SRC)
    .filter((p) => !dictFiles.has(p))
    .map((p) => readFileSync(p, 'utf8'))
    .join('\n');
  // dynamic prefixes: t(`foo.bar.${x}`) → every key starting with `foo.bar.` counts as used
  const prefixes = [...code.matchAll(/`([a-z0-9_.]+\.)\$\{/g)].map((m) => m[1]);
  const out = [];
  for (const d of dicts) {
    for (const e of d.es) {
      const k = e.key;
      if (code.includes(`'${k}'`) || code.includes(`"${k}"`) || code.includes(`\`${k}\``)) continue;
      if (prefixes.some((p) => k.startsWith(p))) continue;
      // keys used through `${prefix}${suffix}` maps (e.g. STEP_TITLE[id]) are listed as values in code
      out.push({ file: d.file, key: k });
    }
  }
  return out;
}

/* ------------------------------------------------------------------- main */

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const baseline = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : { cross_file_duplicates: [] };
  const dicts = DICTIONARIES.map(([f, es, en]) => loadDictionary(f, es, en));
  const problems = runChecks(dicts, baseline);
  const unused = unusedKeys(dicts);
  const total = dicts.reduce((n, d) => n + d.es.length, 0);
  if (process.argv.includes('--json')) {
    console.log(JSON.stringify({ files: dicts.map((d) => ({ file: d.file, es: d.es.length, en: d.en.length })), problems, unused, baseline }, null, 2));
  } else {
    for (const d of dicts) console.log(`${d.file.padEnd(34)} es=${d.es.length} en=${d.en.length}`);
    console.log(`\n${total} keys across ${dicts.length} files; baseline tolerates ${baseline.cross_file_duplicates.length} cross-file duplicate(s): ${baseline.cross_file_duplicates.join(', ') || '—'}`);
    for (const p of problems) console.log(`FAIL  ${p.kind}: ${p.key}  (${p.file}${p.side ? ' ' + p.side : ''})${p.detail ? '  ' + p.detail : ''}`);
    console.log(`\nunused keys (non-fatal): ${unused.length}`);
    if (process.argv.includes('--unused')) for (const u of unused) console.log(`  ${u.key}  (${u.file})`);
    console.log(problems.length ? `\ncheck-i18n: ${problems.length} problem(s)` : '\ncheck-i18n: OK');
  }
  process.exit(problems.length ? 1 : 0);
}
