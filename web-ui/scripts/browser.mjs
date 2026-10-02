/**
 * Shared headless-browser launcher for ui-check.mjs (and anything else that needs a real
 * Chrome): `puppeteer-core` driving the browser already on the machine — nothing is ever
 * downloaded, so it works offline and the same code runs on Windows and macOS.
 *
 * The probe list is the one screenshots.mjs uses; `CHROME_PATH` wins when set. When no browser
 * is found, `launch()` throws `NoBrowserError` and callers exit 3 (screenshots.mjs exits 0
 * because a missing browser must not fail a *build*; a *check* that cannot run must say so).
 */
import { existsSync } from 'node:fs';

export class NoBrowserError extends Error {
  constructor() {
    super('No Chrome/Edge/Chromium found. Set CHROME_PATH to the browser executable.');
    this.name = 'NoBrowserError';
  }
}

export const CHROME_CANDIDATES = [
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

/** The first executable that exists, or null. */
export function findChrome() {
  return CHROME_CANDIDATES.find((p) => existsSync(p)) ?? null;
}

/**
 * Launch headless Chrome through puppeteer-core. Returns the Browser; the caller closes it.
 * Extra launch args go in `args` (e.g. `--lang=es-MX`).
 */
export async function launch({ args = [], headless = true } = {}) {
  const executablePath = findChrome();
  if (!executablePath) throw new NoBrowserError();
  let puppeteer;
  try {
    puppeteer = (await import('puppeteer-core')).default;
  } catch {
    throw new Error('puppeteer-core is not installed — run `npm ci` in web-ui/.');
  }
  return puppeteer.launch({
    executablePath,
    headless: headless ? 'new' : false,
    args: ['--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars', ...args],
  });
}
