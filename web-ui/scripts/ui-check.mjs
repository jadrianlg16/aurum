#!/usr/bin/env node
/**
 * Headless UI check for the personal product.
 *
 * Drives the real browser on this machine (scripts/browser.mjs, puppeteer-core, nothing
 * downloaded) through every personal route at four widths and both themes, and asserts:
 *   - no horizontal overflow: `document.scrollingElement.scrollWidth <= viewport width`;
 *   - 0 console errors / page errors;
 *   - 0 HTTP responses ≥ 400;
 *   - axe-core `wcag2a` + `wcag2aa` + `wcag22aa`: 0 serious/critical violations;
 *   - tap targets ≥ 44×44 below 960px (coarse pointer / narrow), ≥ 36×36 at ≥960px with a fine
 *     pointer — the same rule as globals.css `(pointer: coarse), (max-width: 959px)`;
 *     inline text links allow-listed;
 *   - simple mode: no banned vocabulary in the rendered text (rules from check-vocab.mjs);
 * writes `docs/screenshots/ui/<route>-<width>-<theme>.png` (repo root, gitignored) and a JSON
 * report next to them.
 *
 * Config (env, nothing machine-specific):
 *   BASE_URL      default http://localhost:5024 (the compose stack); mock build: :3000
 *   WS            REQUIRED. `personal` is refused (exit 2) before any request.
 *   CHROME_PATH   browser executable when the probe list misses it.
 * Flags:
 *   --mock        the in-browser fake API (skips --flows, treats the workspace as simple mode)
 *   --a11y        dialog keyboard contract (Esc closes, focus returns, Enter submits) + 'n'
 *   --flows       creates `ui-check-<ts>` through the API, walks day-one / Tuesday / month-end
 *                 and asserts against the API's own figures; marks the workspace hidden after
 *   --routes a,b  --widths 390,1280  --themes light  --out report.json  --no-shots  --quiet
 * Exit codes: 0 ok · 1 assertion failed · 2 refused (WS) · 3 no browser.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NoBrowserError, launch } from './browser.mjs';
import { DEFAULT_BANNED, loadRules } from './check-vocab.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const SHOTS = path.join(REPO, 'docs', 'screenshots', 'ui');
const AXE_PATH = path.resolve(HERE, '..', 'node_modules', 'axe-core', 'axe.min.js');

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const opt = (name, fallback) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
};

const BASE_URL = (process.env.BASE_URL ?? 'http://localhost:5024').replace(/\/$/, '');
const WS = process.env.WS ?? '';
const MOCK = flag('--mock');
const QUIET = flag('--quiet');
const NO_SHOTS = flag('--no-shots');
const OUT = opt('--out', path.join(SHOTS, 'report.json'));

const ALL_ROUTES = [
  '/',
  '/movimientos/',
  '/cuentas/',
  '/presupuesto/',
  '/metas/',
  '/categorias/',
  '/money/',
  '/money/?tab=subs',
  '/money/?tab=calendar',
  '/money/?tab=flow',
  '/money/?tab=plan',
  '/money/?tab=income',
  '/empezar/',
  '/settings/',
  '/avanzado/',
];
/**
 * The Avanzado page is the one screen a simple workspace reaches where the technical names
 * (CFDI, RESICO, Libros, Bandeja) belong — design-system.md §1, "Avanzado". Every other check
 * still runs on it; only the banned-vocabulary scan skips it.
 */
const VOCAB_EXEMPT = new Set(['/avanzado/']);
const ROUTES = opt('--routes', '').split(',').filter(Boolean).length ? opt('--routes', '').split(',') : ALL_ROUTES;
const WIDTHS = opt('--widths', '320,390,768,1280').split(',').map(Number);
const THEMES = opt('--themes', 'light,dark').split(',');
const TAP_MIN = 44;
/** Same breakpoint as globals.css: a fine pointer at ≥960px gets 36px controls (design-system.md §3). */
const TAP_MIN_FINE = 36;
const tapMinFor = (width) => (width < 960 ? TAP_MIN : TAP_MIN_FINE);

/* ------------------------------------------------------------- refusals */

if (!WS) {
  console.error('ui-check: WS is required (e.g. WS=demo-mx). Never `personal`.');
  process.exit(2);
}
if (WS === 'personal' || (process.env.AURUM_PROTECTED_WORKSPACES ?? 'personal').split(',').includes(WS)) {
  console.error(`ui-check: refusing to run against the protected workspace '${WS}'. No request was made.`);
  process.exit(2);
}

const routeName = (r) =>
  (r === '/' ? 'home' : r.replace(/^\//, '').replace(/\/$/, '').replace(/\/\?tab=/, '-').replace(/[^a-z0-9-]/gi, '-')) || 'home';

const log = (...a) => {
  if (!QUIET) console.log(...a);
};

/* ------------------------------------------------------------ in-page JS */

/** Interactive elements smaller than the tap minimum (inline links inside text are allowed). */
const TAP_AUDIT = (min) => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab], [role=menuitem], [role=switch], [role=checkbox]';
  const inline = new Set(['P', 'LI', 'TD', 'TH', 'SPAN', 'SMALL', 'LABEL', 'DD', 'DT', 'EM', 'STRONG', 'H1', 'H2', 'H3', 'H4', 'FIGCAPTION', 'SUMMARY']);
  const out = [];
  let total = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (el.closest('[hidden], [aria-hidden="true"]')) continue;
    total += 1;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if ((type === 'checkbox' || type === 'radio') && (el.labels?.length || el.closest('label'))) continue;
    if (el.tagName === 'A' && inline.has(el.parentElement?.tagName) && cs.display.startsWith('inline')) continue;
    if (el.tagName === 'A' && el.matches('.skip')) continue;
    if (r.width + 0.5 < min || r.height + 0.5 < min) {
      out.push({ tag: el.tagName.toLowerCase(), text: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40), w: Math.round(r.width), h: Math.round(r.height) });
    }
  }
  return { total, failures: out };
};

const PAGE_METRICS = () => {
  // The vocabulary scan reads UI copy, not data: <select> options (the workspace switcher lists every
  // workspace name, e.g. the seeded 'Demo México (RESICO)') and [data-user-content] are hidden while
  // innerText is read, so a person's own names never trip a banned-word rule.
  const skip = [...document.querySelectorAll('select, [data-user-content]')];
  const prev = skip.map((el) => el.style.visibility);
  skip.forEach((el) => { el.style.visibility = 'hidden'; });
  const text = document.body ? document.body.innerText : '';
  skip.forEach((el, i) => { el.style.visibility = prev[i]; });
  return {
    scrollWidth: document.scrollingElement.scrollWidth,
    innerWidth: window.innerWidth,
    title: document.title,
    text,
  };
};

/* ------------------------------------------------------------ one route */

async function checkRoute(browser, route, width, theme, ctx) {
  const page = await browser.newPage();
  const consoleErrors = [];
  const http = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300));
  });
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on('response', (res) => {
    const status = res.status();
    if (status >= 400) http.push({ status, url: res.url().replace(BASE_URL, '') });
  });
  await page.evaluateOnNewDocument(
    (ws, th) => {
      try {
        localStorage.setItem('aurum.ws', ws);
        localStorage.setItem('aurum.workspace', ws); // legacy key, for older builds
        localStorage.setItem('aurum.theme', th);
        localStorage.setItem('aurum.lang', 'es');
      } catch {
        /* ignore */
      }
    },
    WS,
    theme,
  );
  if (MOCK) {
    // The fake API answers inside the page (window.fetch is patched), so the network never
    // sees its 4xx/5xx. Trap the patched fetch and record what it answered.
    await page.evaluateOnNewDocument(() => {
      window.__mockHttp = [];
      let inner = window.fetch;
      Object.defineProperty(window, 'fetch', {
        configurable: true,
        get() {
          return inner;
        },
        set(v) {
          inner = (input, init) => {
            const url = typeof input === 'string' ? input : input && input.url ? input.url : String(input);
            return v(input, init).then((res) => {
              if (url.includes('/api/') && res.status >= 400) window.__mockHttp.push({ status: res.status, url });
              return res;
            });
          };
        },
      });
    });
  }
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: theme }]);
  await page.setViewport({ width, height: 900, deviceScaleFactor: 1, isMobile: width < 768, hasTouch: width < 768 });

  const result = { route, width, theme, ok: true, problems: [] };
  try {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle0', timeout: 45_000 });
    await new Promise((r) => setTimeout(r, 400));
    const metrics = await page.evaluate(PAGE_METRICS);
    result.title = metrics.title;
    // Under mobile emulation Chrome grows the layout viewport (innerWidth) to the content, so
    // the honest bound is the emulated viewport width itself: anything wider scrolls sideways.
    result.overflow = { scrollWidth: metrics.scrollWidth, innerWidth: metrics.innerWidth, viewport: width, ok: metrics.scrollWidth <= width };
    if (!result.overflow.ok) result.problems.push(`overflow ${metrics.scrollWidth}px > ${width}px viewport`);

    result.console = consoleErrors;
    if (consoleErrors.length) result.problems.push(`${consoleErrors.length} console error(s)`);
    if (MOCK) {
      const inPage = await page.evaluate(() => window.__mockHttp || []);
      http.push(...inPage);
    }
    result.http = http;
    if (http.length) result.problems.push(`${http.length} response(s) ≥ 400`);

    const tapMin = tapMinFor(width);
    const tap = await page.evaluate(TAP_AUDIT, tapMin);
    result.tap = { min: tapMin, total: tap.total, failures: tap.failures.length, samples: tap.failures.slice(0, 8) };
    if (tap.failures.length) result.problems.push(`${tap.failures.length}/${tap.total} tap target(s) < ${tapMin}px`);

    if (ctx.simpleMode && !VOCAB_EXEMPT.has(route)) {
      const hits = [];
      for (const re of ctx.banned) {
        const m = re.exec(metrics.text);
        if (m) hits.push({ rule: re.source, match: m[0] });
      }
      result.vocab = hits;
      if (hits.length) result.problems.push(`banned vocabulary on screen: ${hits.map((h) => JSON.stringify(h.match)).join(', ')}`);
    }

    if (ctx.axeSource) {
      await page.addScriptTag({ content: ctx.axeSource });
      const axe = await page.evaluate(async () => {
        const r = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag22aa'] } });
        return r.violations
          .filter((v) => v.impact === 'serious' || v.impact === 'critical')
          .map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.target?.join(' ') ?? '' }));
      });
      result.axe = axe;
      if (axe.length) result.problems.push(`axe: ${axe.map((v) => `${v.id}×${v.nodes}`).join(', ')}`);
    }

    if (!NO_SHOTS) {
      mkdirSync(SHOTS, { recursive: true });
      const file = path.join(SHOTS, `${routeName(route)}-${width}-${theme}.png`);
      await page.screenshot({ path: file, fullPage: true });
      result.screenshot = path.relative(REPO, file).replace(/\\/g, '/');
    }
  } catch (e) {
    result.problems.push(`load failed: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    await page.close();
  }
  result.ok = result.problems.length === 0;
  return result;
}

/* ------------------------------------------------------------- --a11y */

async function dialogContract(browser, ctx) {
  const out = { name: 'a11y', steps: [], ok: true };
  const step = (name, ok, detail = '') => {
    out.steps.push({ name, ok, detail });
    if (!ok) out.ok = false;
  };
  const page = await browser.newPage();
  await page.evaluateOnNewDocument((ws) => {
    localStorage.setItem('aurum.ws', ws);
    localStorage.setItem('aurum.workspace', ws);
  }, WS);
  await page.setViewport({ width: 1280, height: 900 });
  try {
    await page.goto(`${BASE_URL}/movimientos/`, { waitUntil: 'networkidle0', timeout: 45_000 });
    const openDialog = () => page.evaluate(() => {
      const d = document.querySelector('dialog[open], [role=dialog]:not([hidden])');
      return d ? { tag: d.tagName.toLowerCase(), hasForm: d.matches('form') || !!d.querySelector('form'), submit: !!d.querySelector('button[type=submit], form button:not([type=button])') } : null;
    });
    // 1. Focus the primary "+ Agregar" button and open it with Enter.
    const focused = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button, a')].find((b) => /\+\s*Agregar|Agregar/i.test(b.textContent || '') && !b.closest('dialog'));
      if (!btn) return false;
      btn.id = btn.id || 'ui-check-opener';
      btn.focus();
      return document.activeElement === btn;
    });
    step('"+ Agregar" button focusable', focused);
    await page.keyboard.press('Enter');
    await new Promise((r) => setTimeout(r, 300));
    let d = await openDialog();
    step('Enter on the opener shows a dialog', !!d, d ? JSON.stringify(d) : 'no dialog[open]/[role=dialog]');
    step('dialog is in form mode (has a form + submit)', !!d && d.hasForm && d.submit);
    // 2. Esc closes and focus returns to the opener.
    await page.keyboard.press('Escape');
    await new Promise((r) => setTimeout(r, 300));
    d = await openDialog();
    step('Esc closes the dialog', !d);
    const back = await page.evaluate(() => document.activeElement?.id === 'ui-check-opener');
    step('focus returns to the opener after Esc', back);
    // 3. 'n' opens + Agregar from the page …
    await page.evaluate(() => document.body.focus());
    await page.keyboard.press('n');
    await new Promise((r) => setTimeout(r, 300));
    d = await openDialog();
    step("'n' opens + Agregar", !!d);
    if (d) {
      await page.keyboard.press('Escape');
      await new Promise((r) => setTimeout(r, 200));
    }
    // 4. … but not while typing.
    const typed = await page.evaluate(() => {
      const input = document.querySelector('input[type=search], input[type=text], input:not([type])');
      if (!input) return 'no-input';
      input.focus();
      return document.activeElement === input;
    });
    if (typed === true) {
      await page.keyboard.press('n');
      await new Promise((r) => setTimeout(r, 300));
      d = await openDialog();
      step("'n' does nothing while typing in an input", !d);
    } else step("'n' does nothing while typing in an input", false, 'no text input on /movimientos/ to type in');
  } catch (e) {
    step('dialog contract ran', false, e instanceof Error ? e.message : String(e));
  } finally {
    await page.close();
  }
  void ctx;
  return out;
}

/* ------------------------------------------------------------- --flows */

async function api(method, p, body) {
  const res = await fetch(`${BASE_URL}/api${p}`, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try {
    json = text ? JSON.parse(text) : undefined;
  } catch {
    json = text;
  }
  if (!res.ok) throw new Error(`${method} ${p} → ${res.status} ${typeof json === 'string' ? json : JSON.stringify(json)}`);
  return json;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function flows(browser) {
  const out = { name: 'flows', ws: null, steps: [], ok: true };
  const step = (name, ok, detail = '') => {
    out.steps.push({ name, ok, detail });
    if (!ok) out.ok = false;
  };
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14).toLowerCase();
  const id = `ui-check-${ts}`;
  out.ws = id;
  let page;
  try {
    await api('POST', '/workspaces', { id, name: `ui-check ${ts}`, kind: 'personal', jurisdictions: ['MX'], base_currency: 'MXN', language: 'es', profile: {} });
    step('workspace created through the API', true, id);
    page = await browser.newPage();
    await page.evaluateOnNewDocument((ws) => {
      localStorage.setItem('aurum.ws', ws);
      localStorage.setItem('aurum.workspace', ws);
    }, id);
    await page.setViewport({ width: 1280, height: 900 });

    /* ---- Day one: an account, then the first expense through "+ Agregar". */
    const acct = await api('POST', `/pf/${id}/accounts`, { name: 'Banco', type: 'checking', currency: 'MXN', opening_balance: { amount: '10000.00', currency: 'MXN' } });
    await page.goto(`${BASE_URL}/movimientos/`, { waitUntil: 'networkidle0', timeout: 45_000 });
    const opened = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => /Agregar/i.test(b.textContent || '') && !b.closest('dialog'));
      if (!btn) return false;
      btn.click();
      return true;
    });
    step('day-one: "+ Agregar" opens', opened);
    await wait(400);
    const filled = await page.evaluate(() => {
      const dlg = document.querySelector('dialog[open], [role=dialog]');
      if (!dlg) return 'no dialog';
      const amount = dlg.querySelector('input[inputmode=decimal], input[name=amount]');
      if (!amount) return 'no amount input';
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(amount, '250.00');
      amount.dispatchEvent(new Event('input', { bubbles: true }));
      amount.focus();
      return true;
    });
    step('day-one: amount typed into the dialog', filled === true, String(filled));
    await page.keyboard.press('Enter');
    await wait(1200);
    const entries = await api('GET', `/pf/${id}/entries`);
    const rows = Array.isArray(entries) ? entries : entries.entries ?? [];
    const totals = Array.isArray(entries) ? null : entries.totals;
    step('day-one: one entry persisted (GET /entries)', rows.length === 1, `count=${rows.length}`);
    // totals.out is Σ|amount|, positive (aurum/pf/entries.py); the UI renders the sign, never the API
    step('day-one: totals.out = 250.00 (server figure)', totals?.out?.amount === '250.00', JSON.stringify(totals));

    /* ---- Tuesday: a fixed payment due today, marked paid from the calendar. */
    const today = new Date();
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    await api('POST', `/organizer/${id}/commitments`, { kind: 'bill', name: 'Internet', amount: { amount: '499.00', currency: 'MXN' }, cadence: 'monthly', anchor_day: today.getDate(), next_due: iso, account_id: acct.id, essential: 'needs' });
    const before = await api('GET', `/organizer/${id}/summary`);
    // Inicio's "Lo que viene" keeps the one-tap 'Pagado' Button for fixed due rows. Resumen is
    // an advanced-mode tab, so the flow targets Inicio.
    await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle0', timeout: 45_000 });
    const paid = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => /^Pagado$/i.test((b.textContent || '').trim()));
      if (!btn) return false;
      btn.click();
      return true;
    });
    step('tuesday: a "Pagado" button exists for today\'s occurrence', paid);
    await wait(1200);
    const after = await api('GET', `/organizer/${id}/summary`);
    const entries2 = await api('GET', `/pf/${id}/entries`);
    const rows2 = Array.isArray(entries2) ? entries2 : entries2.entries ?? [];
    const linked = rows2.find((e) => e.commitment_id);
    step('tuesday: the paid occurrence created an entry stamped commitment_id', !!linked, linked ? linked.id : `rows=${rows2.length}`);
    step('tuesday: safe_to_spend changed (server figure)', before.safe_to_spend?.amount !== after.safe_to_spend?.amount, `${before.safe_to_spend?.amount} → ${after.safe_to_spend?.amount}`);

    /* ---- Month end: copy last month's budgets. */
    const y = today.getFullYear();
    const m = today.getMonth();
    const period = `${y}-${String(m + 1).padStart(2, '0')}`;
    const prevDate = new Date(y, m - 1, 1);
    const prev = `${prevDate.getFullYear()}-${String(prevDate.getMonth() + 1).padStart(2, '0')}`;
    const labels = await api('GET', `/pf/${id}/labels?kind=expense`);
    const label = (Array.isArray(labels) ? labels : [])[0];
    step('month-end: an expense category exists to budget', !!label);
    if (label) {
      await api('POST', `/pf/${id}/budgets`, { label_id: label.id, period: prev, amount: '1500.00', currency: 'MXN', rollover: false });
      await page.goto(`${BASE_URL}/presupuesto/`, { waitUntil: 'networkidle0', timeout: 45_000 });
      const copied = await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find((b) => /Copiar del mes anterior/i.test(b.textContent || ''));
        if (!btn) return false;
        btn.click();
        return true;
      });
      step('month-end: "Copiar del mes anterior" button exists', copied);
      await wait(1200);
      const now = await api('GET', `/pf/${id}/budgets?period=${period}`);
      step('month-end: the budget was copied into the current month (GET /budgets)', Array.isArray(now) && now.length === 1, `count=${Array.isArray(now) ? now.length : '?'}`);
      const again = await api('POST', `/pf/${id}/budgets/copy`, { from: prev, to: period });
      step('month-end: a second copy is idempotent (created 0, skipped 1)', again.created === 0 && again.skipped === 1, JSON.stringify(again));
    }
  } catch (e) {
    step('flows ran', false, e instanceof Error ? e.message : String(e));
  } finally {
    if (page) await page.close();
    try {
      await api('PUT', `/workspaces/${id}`, { hidden: true });
      step('workspace marked hidden in finally', true);
    } catch (e) {
      step('workspace marked hidden in finally', false, e instanceof Error ? e.message : String(e));
    }
  }
  return out;
}

/* ------------------------------------------------------------------ main */

async function main() {
  let browser;
  try {
    browser = await launch({ args: ['--lang=es-MX'] });
  } catch (e) {
    if (e instanceof NoBrowserError) {
      console.error(`ui-check: ${e.message}`);
      process.exit(3);
    }
    throw e;
  }

  let simpleMode = true;
  if (!MOCK) {
    try {
      const w = await api('GET', `/workspaces/${WS}`);
      simpleMode = w?.ui_mode !== 'advanced';
    } catch (e) {
      console.error(`ui-check: cannot read ${BASE_URL}/api/workspaces/${WS}: ${e instanceof Error ? e.message : e}`);
      await browser.close();
      process.exit(2);
    }
  }
  const rules = loadRules();
  const banned = (rules.banned ?? DEFAULT_BANNED).map((r) => new RegExp(r));
  let axeSource = null;
  try {
    axeSource = readFileSync(AXE_PATH, 'utf8');
  } catch {
    console.warn('ui-check: axe-core not installed (npm ci) — skipping the axe audit');
  }
  const ctx = { simpleMode, banned, axeSource };

  const report = { base_url: BASE_URL, ws: WS, mock: MOCK, started: new Date().toISOString(), simple_mode: simpleMode, results: [], extra: [] };
  log(`ui-check: ${BASE_URL} ws=${WS} routes=${ROUTES.length} widths=${WIDTHS.join('/')} themes=${THEMES.join('/')}${MOCK ? ' (mock)' : ''}`);
  log('');
  log('route                  width theme  scroll/vw     console  >=400  axe  tap   vocab  result');
  for (const route of ROUTES) {
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        const r = await checkRoute(browser, route, width, theme, ctx);
        report.results.push(r);
        const ov = r.overflow ? `${r.overflow.scrollWidth}/${r.overflow.viewport}` : 'n/a';
        log(
          `${route.padEnd(22)} ${String(width).padStart(5)} ${theme.padEnd(6)} ${ov.padEnd(13)} ${String(r.console?.length ?? '-').padStart(7)}  ${String(r.http?.length ?? '-').padStart(5)}  ${String(r.axe?.length ?? '-').padStart(3)}  ${String(r.tap?.failures ?? '-').padStart(4)}  ${String(r.vocab?.length ?? '-').padStart(5)}  ${r.ok ? 'ok' : 'FAIL'}`,
        );
      }
    }
  }

  if (flag('--a11y')) report.extra.push(await dialogContract(browser, ctx));
  if (flag('--flows') && !MOCK) report.extra.push(await flows(browser));
  else if (flag('--flows') && MOCK) log('\n--flows skipped in --mock mode (no API to create a workspace on)');

  await browser.close();

  const failed = report.results.filter((r) => !r.ok);
  const extraFailed = report.extra.filter((x) => !x.ok);
  report.summary = { pages: report.results.length, failed: failed.length, extra_failed: extraFailed.length };
  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(report, null, 2) + '\n');

  log('');
  for (const r of failed) log(`FAIL ${r.route} @${r.width} ${r.theme}: ${r.problems.join('; ')}`);
  for (const x of report.extra) {
    log(`\n${x.name}: ${x.ok ? 'ok' : 'FAIL'}${x.ws ? ` (workspace ${x.ws})` : ''}`);
    for (const s of x.steps) log(`  ${s.ok ? 'ok  ' : 'FAIL'} ${s.name}${s.detail ? ` — ${s.detail}` : ''}`);
  }
  log(`\nui-check: ${report.results.length - failed.length}/${report.results.length} page loads clean${report.extra.length ? `, ${report.extra.length - extraFailed.length}/${report.extra.length} extra suites ok` : ''}; report ${path.relative(process.cwd(), OUT)}`);
  process.exit(failed.length || extraFailed.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
