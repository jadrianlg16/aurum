/**
 * Contrast pairs: the design palette must pass the whole pair
 * table in both themes, and the checker must call the known-bad old value out.
 * `scripts/contrast.mjs` is the gate on the real globals.css; this pins its maths and table.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { BOUNDARY_PAIRS, TEXT_PAIRS, checkCss, checkPalette, contrastRatio, parseTokens } from '../scripts/contrast.mjs';

/** The design tokens (design-system.md §3) — light and dark exactly as defined. */
const TOKENS_LIGHT: Record<string, string> = {
  '--paper': '#f7f6f3', '--surface': '#fff', '--surface-2': '#f1efe9', '--line': '#d6d2c8', '--line-strong': '#8f8a7e',
  '--ink': '#1c1a17', '--ink-2': '#4f4a43', '--ink-3': '#6b665e', '--accent-text': '#7d5e0f', '--accent': '#b8860b',
  '--on-accent': '#1c1a17', '--accent-soft': '#f3e7c9', '--pos': '#1b6b45', '--pos-soft': '#e2f1e9', '--neg': '#a52a20',
  '--neg-soft': '#f8e5e3', '--warn': '#8a5a06', '--warn-soft': '#fbeed2', '--info': '#245582', '--info-soft': '#e2edf6',
};
const TOKENS_DARK: Record<string, string> = {
  '--paper': '#141312', '--surface': '#1c1b19', '--surface-2': '#242220', '--line': '#3a3732', '--line-strong': '#726d63',
  '--ink': '#efebe3', '--ink-2': '#c2bbb0', '--ink-3': '#a09a90', '--accent-text': '#e0b455', '--accent': '#d8ac4e',
  '--on-accent': '#1c1a17', '--accent-soft': '#3a2f16', '--pos': '#6fc99d', '--pos-soft': '#17291f', '--neg': '#f0908a',
  '--neg-soft': '#2f1b1a', '--warn': '#e0b45a', '--warn-soft': '#2c2415', '--info': '#8dbde6', '--info-soft': '#17242f',
};

describe('contrast maths', () => {
  it('matches the WCAG reference values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 2);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });
  it('flags the old --ink-3 #857f76 on white at 3.97', () => {
    expect(contrastRatio('#857f76', '#ffffff')).toBeCloseTo(3.97, 2);
  });
});

describe('the design palette', () => {
  it('passes every text pair (>= 4.5) and boundary pair (>= 3) in light', () => {
    const rows = checkPalette(TOKENS_LIGHT, 'light');
    expect(rows.length).toBe(TEXT_PAIRS.length + BOUNDARY_PAIRS.length);
    expect(rows.filter((r) => !r.ok).map((r) => `${r.fg} on ${r.bg} = ${r.ratio}`)).toEqual([]);
  });
  it('passes every pair in dark', () => {
    const rows = checkPalette(TOKENS_DARK, 'dark');
    expect(rows.filter((r) => !r.ok).map((r) => `${r.fg} on ${r.bg} = ${r.ratio}`)).toEqual([]);
  });
});

describe('globals.css parsing', () => {
  const css = readFileSync(path.resolve(__dirname, '..', 'src', 'app', 'globals.css'), 'utf8');
  type Vars = Record<string, string>;
  it('separates the light :root block from the dark media/toggle blocks', () => {
    const { light, dark } = parseTokens(css) as unknown as { light: Vars; dark: Vars };
    expect(light['--paper']).toMatch(/^#/);
    expect(dark['--paper']).toMatch(/^#/);
    expect(light['--paper']).not.toBe(dark['--paper']);
  });
  it('produces one row per pair per theme', () => {
    expect(checkCss(css).length).toBe(2 * (TEXT_PAIRS.length + BOUNDARY_PAIRS.length));
  });
  it('resolves var() aliases', () => {
    const { light } = parseTokens(':root{--a:#000;--b:var(--a);--paper:#fff;}') as unknown as { light: Vars };
    expect(light['--b']).toBe('var(--a)');
    expect(checkPalette({ '--ink': 'var(--x)', '--x': '#000', '--paper': '#fff' }, 'light').find((r) => r.fg === '--ink' && r.bg === '--paper')?.ok).toBe(true);
  });
});
