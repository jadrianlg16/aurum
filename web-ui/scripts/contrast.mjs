#!/usr/bin/env node
/**
 * WCAG 2.1 contrast gate for the design tokens.
 *
 * Parses `src/app/globals.css` by regex (no PostCSS): the light palette is the first `:root {}`
 * block, the dark palette is every block inside `@media (prefers-color-scheme: dark)` plus
 * `:root[data-theme='dark'] {}`, merged over the light one (so aliases resolve). Then asserts
 * the pair table below: text pairs ≥ 4.5, boundary pairs ≥ 3, for both themes.
 *
 * Prints one `PASS/FAIL  ratio  --fg on --bg (theme)` line per pair and exits 1 on any FAIL.
 * Wired into `npm run lint:ui`. The old palette failed it (`--ink-3 #857f76` on paper = 3.97);
 * the current tokens pass every pair.
 *
 *   node scripts/contrast.mjs            # gate
 *   node scripts/contrast.mjs --json     # machine-readable
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS = process.env.GLOBALS_CSS ?? path.resolve(HERE, '..', 'src', 'app', 'globals.css');

/** text (≥ 4.5) pairs: [foreground, background]. */
export const TEXT_PAIRS = [
  ['--ink', '--paper'],
  ['--ink', '--surface'],
  ['--ink', '--surface-2'],
  ['--ink-2', '--paper'],
  ['--ink-2', '--surface'],
  ['--ink-2', '--surface-2'],
  ['--ink-3', '--paper'],
  ['--ink-3', '--surface'],
  ['--ink-3', '--surface-2'],
  ['--accent-text', '--paper'],
  ['--accent-text', '--surface'],
  ['--on-accent', '--accent'],
  ['--pos', '--paper'],
  ['--pos', '--pos-soft'],
  ['--neg', '--paper'],
  ['--neg', '--neg-soft'],
  ['--warn', '--paper'],
  ['--warn', '--warn-soft'],
  ['--info', '--paper'],
  ['--info', '--info-soft'],
];

/** non-text boundaries (≥ 3): borders, focus rings, filled controls. */
export const BOUNDARY_PAIRS = [
  ['--line-strong', '--paper'],
  ['--line-strong', '--surface'],
  ['--accent', '--paper'],
  ['--accent', '--surface'],
];

/** Legacy token names the pair table falls back to (reported as "via alias"). */
const LEGACY_ALIASES = {
  '--accent-text': '--gold',
  '--accent': '--gold',
  '--accent-soft': '--gold-soft',
  '--on-accent': '--paper',
};

/* --------------------------------------------------------------- parsing */

/** Every `--name: value;` inside the block starting at `open` (index of `{`). */
function blockVars(css, open) {
  let depth = 0;
  let i = open;
  for (; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    else if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  const body = css.slice(open + 1, i);
  const vars = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) vars[m[1]] = m[2].trim();
  return { vars, end: i };
}

export function parseTokens(css) {
  const stripped = css.replace(/\r\n?/g, '\n').replace(/\/\*[\s\S]*?\*\//g, '');
  const light = {};
  const dark = {};

  // Light: every top-level `:root {}` — column 0, so the indented one inside the dark media
  // query is not swallowed into the light palette.
  const rootRe = /(^|\n):root\s*\{/g;
  let m;
  while ((m = rootRe.exec(stripped))) {
    const open = stripped.indexOf('{', m.index);
    const { vars, end } = blockVars(stripped, open);
    Object.assign(light, vars);
    rootRe.lastIndex = end;
  }

  // Dark: blocks inside `@media (prefers-color-scheme: dark) { ... }`.
  const mediaRe = /@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{/g;
  while ((m = mediaRe.exec(stripped))) {
    const open = stripped.indexOf('{', m.index);
    const { end } = blockVars(stripped, open);
    const inner = stripped.slice(open + 1, end);
    const innerRe = /:root[^{]*\{/g;
    let n;
    while ((n = innerRe.exec(inner))) {
      const o = inner.indexOf('{', n.index);
      const r = blockVars(inner, o);
      Object.assign(dark, r.vars);
      innerRe.lastIndex = r.end;
    }
    mediaRe.lastIndex = end;
  }

  // Dark: the explicit toggle selector.
  const toggleRe = /:root\[data-theme=['"]dark['"]\][^{]*\{/g;
  while ((m = toggleRe.exec(stripped))) {
    const open = stripped.indexOf('{', m.index);
    const { vars, end } = blockVars(stripped, open);
    Object.assign(dark, vars);
    toggleRe.lastIndex = end;
  }

  return { light, dark: { ...light, ...dark } };
}

/** Resolve `var(--x)` chains and legacy aliases to a hex colour, or null. */
export function resolveColor(vars, name, seen = new Set()) {
  if (seen.has(name)) return null;
  seen.add(name);
  let v = vars[name];
  if (v === undefined) {
    const alias = LEGACY_ALIASES[name];
    return alias ? resolveColor(vars, alias, seen) : null;
  }
  const ref = /^var\((--[a-z0-9-]+)\)$/i.exec(v.trim());
  if (ref) return resolveColor(vars, ref[1], seen);
  v = v.trim();
  return /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(v) ? v : null;
}

/* ---------------------------------------------------------------- maths */

export function hexToRgb(hex) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function channel(c) {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function luminance(hex) {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.1 contrast ratio, 1..21. */
export function contrastRatio(fg, bg) {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

/* ---------------------------------------------------------------- check */

export function checkPalette(vars, theme) {
  const rows = [];
  const run = (pairs, min, kind) => {
    for (const [fg, bg] of pairs) {
      const f = resolveColor(vars, fg);
      const b = resolveColor(vars, bg);
      if (!f || !b) {
        rows.push({ theme, kind, fg, bg, ratio: null, min, ok: false, note: `missing ${!f ? fg : bg}` });
        continue;
      }
      const ratio = Math.round(contrastRatio(f, b) * 100) / 100;
      const via = (!(fg in vars) && LEGACY_ALIASES[fg]) || (!(bg in vars) && LEGACY_ALIASES[bg]);
      rows.push({ theme, kind, fg, bg, ratio, min, ok: ratio >= min, note: via ? `via alias ${via}` : '' });
    }
  };
  run(TEXT_PAIRS, 4.5, 'text');
  run(BOUNDARY_PAIRS, 3, 'boundary');
  return rows;
}

export function checkCss(css) {
  const { light, dark } = parseTokens(css);
  return [...checkPalette(light, 'light'), ...checkPalette(dark, 'dark')];
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const css = readFileSync(CSS, 'utf8');
  const rows = checkCss(css);
  const json = process.argv.includes('--json');
  if (json) {
    console.log(JSON.stringify({ file: CSS, rows }, null, 2));
  } else {
    for (const r of rows) {
      const ratio = r.ratio === null ? '  n/a' : r.ratio.toFixed(2).padStart(5);
      console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${ratio}  ${r.fg} on ${r.bg}  (${r.theme}, ${r.kind} >= ${r.min})${r.note ? '  ' + r.note : ''}`);
    }
  }
  const failed = rows.filter((r) => !r.ok);
  console.log(`\ncontrast: ${rows.length - failed.length}/${rows.length} pairs pass (${path.relative(process.cwd(), CSS)})`);
  process.exit(failed.length ? 1 : 0);
}
