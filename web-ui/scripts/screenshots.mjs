#!/usr/bin/env node
/**
 * Capture web-ui/docs/screenshots/*.png from a running mock build. The output directory is
 * gitignored: the PNGs are for local review, not committed.
 *
 *   npm run build:mock && npm run serve      # in one shell (PORT defaults to 3000)
 *   npm run screenshots                      # in another
 *
 * Uses the browser already on the machine in headless mode. `puppeteer-core` is used when it
 * is installed (it gives a real "wait for the network to settle"), and when it is not — which
 * is the normal case here, since it is not a dependency — the script falls back to driving
 * Chrome/Edge directly with `--headless=new --screenshot`. Either way nothing is downloaded,
 * so this works offline; if no browser is found at all the script says so and exits 0 rather
 * than failing a build.
 *
 * Config (all env, nothing machine-specific in this file):
 *   BASE_URL     default http://localhost:${PORT ?? 3000}
 *   CHROME_PATH  path to chrome/edge/chromium; probed from the usual locations otherwise
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, '..', 'docs', 'screenshots');
const BASE = process.env.BASE_URL ?? `http://localhost:${process.env.PORT ?? 3000}`;

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);

const SHOTS = [
  { name: 'home', url: `${BASE}/`, width: 1400, height: 1250, what: 'safe-to-spend, net worth, deadlines, goals' },
  { name: 'taxes-month-close', url: `${BASE}/taxes/`, width: 1400, height: 2100, what: 'prefill audit: Aurum vs SAT, diffs, Explain' },
  { name: 'inbox', url: `${BASE}/inbox/`, width: 1400, height: 1100, what: 'keyboard review queue grouped by kind' },
  { name: 'plan-credit', url: `${BASE}/plan/`, width: 1400, height: 1400, what: 'goals with projections' },
  { name: 'research', url: `${BASE}/research/`, width: 1400, height: 900, what: 'ask box and citation cards' },
  { name: 'documents', url: `${BASE}/documents/`, width: 1400, height: 1300, what: 'CFDI table with filters and upload zones' },
  // US tax, cross-border, plan and watch. `?ws=`/`?tab=` are the deep links lib/query.ts reads, which is how
  // a headless capture reaches a tab that is not the screen's default.
  { name: 'taxes-us', url: `${BASE}/taxes/?ws=demo-us&tab=us`, width: 1400, height: 2300, what: 'US organizer: Schedule C, SE tax, quarterly, TX franchise, (verify) chips' },
  { name: 'crossborder', url: `${BASE}/crossborder/?ws=demo-us`, width: 1400, height: 1700, what: 'residency, treaty ladder, FBAR, FEIE vs FTC, flags' },
  { name: 'plan-holdings', url: `${BASE}/plan/?tab=holdings`, width: 1400, height: 1700, what: 'positions, allocation, contributions vs limits, FX' },
  { name: 'plan-scenarios', url: `${BASE}/plan/?tab=scenarios`, width: 1400, height: 1500, what: 'scenario catalog, schema-driven form, sensitivity, Monte Carlo' },
  { name: 'watch-sources', url: `${BASE}/watch/?tab=sources`, width: 1400, height: 1100, what: 'watched sources with fetch-method badges' },

  // Business, avisos, report packs and workflows. demo-biz is the business workspace.
  { name: 'business-kpis', url: `${BASE}/business/?ws=demo-biz&tab=kpis`, width: 1400, height: 1900, what: 'revenue, margin, opex by group, runway, tax reserve with (verify)' },
  { name: 'business-payroll', url: `${BASE}/business/?ws=demo-biz&tab=payroll`, width: 1400, height: 1600, what: 'employees, run form, recorded runs with ISR/IMSS/INFONAVIT/ISN' },
  { name: 'business-invoices', url: `${BASE}/business/?ws=demo-biz&tab=invoices`, width: 1400, height: 1700, what: 'issued vs collected, aging buckets, open invoices, top clients, DSO' },
  { name: 'avisos', url: `${BASE}/avisos/`, width: 1400, height: 2000, what: 'insights by severity, 90-day calendar, Telegram digest' },
  { name: 'reports-packs', url: `${BASE}/reports/`, width: 1400, height: 1500, what: 'report pack catalog, preview, archive' },
  { name: 'workflows', url: `${BASE}/workflows/`, width: 1400, height: 1800, what: 'workflow list, YAML editor, allowed endpoints, AI proposal box' },

  // The "Mi dinero" hub, one shot per tab via `?tab=`. Pinned to
  // demo-mx: the default workspace (demo-biz) has no recurring-commitment data, so the money
  // shots would otherwise render empty.
  { name: 'money-resumen', url: `${BASE}/money/?ws=demo-mx`, width: 1400, height: 1700, what: 'safe to spend until payday, committed by kind, next 7 days, alerts' },
  { name: 'money-subs', url: `${BASE}/money/?ws=demo-mx&tab=subs`, width: 1400, height: 1500, what: 'one-line quick add, filters, sortable commitments table' },
  { name: 'money-calendar', url: `${BASE}/money/?ws=demo-mx&tab=calendar`, width: 1400, height: 1300, what: 'month grid with paid/unpaid dots and week totals' },
  { name: 'money-flow', url: `${BASE}/money/?ws=demo-mx&tab=flow`, width: 1400, height: 1100, what: '90-day forecast, low point, safe to spend, buffer' },
  { name: 'money-plan', url: `${BASE}/money/?ws=demo-mx&tab=plan`, width: 1400, height: 1700, what: 'needs/wants/savings/debt bars, uncategorized bulk labelling, rules' },
  // The personal, manual-first screens. `?add=1` opens the Agregar dialog
  // so the app's most important screen can be captured without driving the UI.
  { name: 'movimientos', url: `${BASE}/movimientos/?ws=demo-mx`, width: 1400, height: 1300, what: 'month arrows, search, filters, totals, source chips, row actions' },
  { name: 'movimientos-agregar', url: `${BASE}/movimientos/?ws=demo-mx&add=1`, width: 1400, height: 1300, what: 'the + Agregar dialog: Gasto/Ingreso/Transferencia, amount first, friendly pickers' },
  { name: 'cuentas', url: `${BASE}/cuentas/?ws=demo-mx`, width: 1400, height: 1100, what: 'account cards with balances, card fields, adjust/edit/archive' },
  { name: 'money-ingresos', url: `${BASE}/money/?ws=demo-mx&tab=income`, width: 1400, height: 900, what: 'income streams with paydays and expected-vs-received' },
  { name: 'empezar', url: `${BASE}/empezar/?ws=demo-mx`, width: 1400, height: 1000, what: 'manual-first onboarding: accounts, income, fixed payments, optional import' },
  { name: 'money-setup', url: `${BASE}/money/?ws=demo-mx&tab=setup`, width: 1400, height: 900, what: '3-step wizard: bank lines, detected candidates, plan' },
];

const chrome = CANDIDATES.find((p) => existsSync(p));
if (!chrome) {
  console.warn('screenshots: no Chrome/Edge/Chromium found (set CHROME_PATH). Skipping — this is not a build failure.');
  process.exit(0);
}

mkdirSync(OUT, { recursive: true });
const profile = mkdtempSync(path.join(tmpdir(), 'aurum-shot-'));

try {
  for (const shot of SHOTS) {
    const file = path.join(OUT, `${shot.name}.png`);
    execFileSync(
      chrome,
      [
        '--headless=new',
        '--disable-gpu',
        '--hide-scrollbars',
        '--no-first-run',
        '--no-default-browser-check',
        `--user-data-dir=${profile}`,
        '--force-device-scale-factor=1.5',
        // Light is the primary identity (paper/ink); without this the shots follow the host OS.
        '--blink-settings=preferredColorScheme=1',
        '--run-all-compositor-stages-before-draw',
        // The mock adds ~60ms per call and each screen fires several; give it room.
        '--virtual-time-budget=9000',
        `--window-size=${shot.width},${shot.height}`,
        `--screenshot=${file}`,
        shot.url,
      ],
      { stdio: 'inherit', timeout: 90_000 },
    );
    console.log(`wrote ${path.relative(process.cwd(), file)}  - ${shot.what}`);
  }
} finally {
  rmSync(profile, { recursive: true, force: true });
}
