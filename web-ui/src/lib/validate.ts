/**
 * Client-side form validation.
 *
 * The money rule ("Money is Decimal", docs/ARCHITECTURE.md) applies to *input* too: an amount
 * the user types stays a string from the keystroke to the request body. Nothing here calls
 * `Number()` on money — the regex is the whole check, and the API does the arithmetic with
 * `Decimal`.
 *
 * Every validator returns a message key (`MsgKey`) or `null`. Screens render the message with
 * `t()`, so validation is bilingual for free.
 */
import type { MsgKey } from './i18n';

/** A signed decimal string with at most two fraction digits: "-1234.56", "0", "12.5". */
export const DECIMAL_RE = /^-?\d{1,15}(\.\d{1,2})?$/;
/** Same, but positive and non-zero — targets, limits, principals. */
export const POSITIVE_DECIMAL_RE = /^\d{1,15}(\.\d{1,2})?$/;
/** An annual rate as a fraction of 1 ("0.2499") or a whole number of points ("24.99"). */
export const RATE_RE = /^\d{1,3}(\.\d{1,6})?$/;
export const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
export const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
/** Beancount account: 2+ colon-separated segments, each starting with an upper-case letter. */
export const ACCOUNT_RE = /^[A-Z][A-Za-z0-9-]*(:[A-Z0-9][A-Za-z0-9-]*)+$/;
/** ISO-4217. */
export const CURRENCY_RE = /^[A-Z]{3}$/;
/** Workspace id — used in URL paths, so keep it filesystem/route safe. */
export const WS_ID_RE = /^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/;

export type FieldError = MsgKey | null;

export const required = (v: string): FieldError => (v.trim() ? null : 'valid.required');

export function decimal(v: string, opts: { positive?: boolean; required?: boolean } = {}): FieldError {
  const s = v.trim();
  if (!s) return opts.required === false ? null : 'valid.required';
  const re = opts.positive ? POSITIVE_DECIMAL_RE : DECIMAL_RE;
  if (!re.test(s)) return opts.positive ? 'valid.decimal_positive' : 'valid.decimal';
  if (opts.positive && /^0(\.0{1,2})?$/.test(s)) return 'valid.decimal_positive';
  return null;
}

export function rate(v: string): FieldError {
  const s = v.trim();
  if (!s) return 'valid.required';
  return RATE_RE.test(s) ? null : 'valid.rate';
}

export function isoDate(v: string, req = true): FieldError {
  const s = v.trim();
  if (!s) return req ? 'valid.required' : null;
  if (!ISO_DATE_RE.test(s)) return 'valid.date';
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const round = dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
  return round ? null : 'valid.date';
}

export function period(v: string): FieldError {
  const s = v.trim();
  if (!s) return 'valid.required';
  return PERIOD_RE.test(s) ? null : 'valid.period';
}

export function account(v: string): FieldError {
  const s = v.trim();
  if (!s) return 'valid.required';
  return ACCOUNT_RE.test(s) ? null : 'valid.account';
}

export function currency(v: string): FieldError {
  const s = v.trim().toUpperCase();
  if (!s) return 'valid.required';
  return CURRENCY_RE.test(s) ? null : 'valid.currency';
}

export function integer(v: string, min = 1, max = 999): FieldError {
  const s = v.trim();
  if (!s) return 'valid.required';
  if (!/^\d{1,4}$/.test(s)) return 'valid.integer';
  const n = Number(s);
  return n >= min && n <= max ? null : 'valid.range';
}

export function workspaceId(v: string): FieldError {
  const s = v.trim();
  if (!s) return 'valid.required';
  return WS_ID_RE.test(s) ? null : 'valid.ws_id';
}

/** True when every field of an error map is null. */
export function isValid(errors: Record<string, FieldError>): boolean {
  return Object.values(errors).every((e) => e === null);
}

/**
 * Sum a list of decimal strings exactly, in integer centavos. Used only to tell the user
 * whether the postings they typed balance — the API recomputes it and is the authority.
 */
export function sumDecimals(values: string[]): string {
  let cents = 0n;
  for (const v of values) {
    const s = v.trim();
    if (!s || !DECIMAL_RE.test(s)) continue;
    const neg = s.startsWith('-');
    const [int = '0', frac = ''] = s.replace(/^-/, '').split('.');
    const c = BigInt(int || '0') * 100n + BigInt((frac + '00').slice(0, 2));
    cents += neg ? -c : c;
  }
  const neg = cents < 0n;
  const abs = neg ? -cents : cents;
  return `${neg ? '-' : ''}${abs / 100n}.${(abs % 100n).toString().padStart(2, '0')}`;
}

export const isZero = (decimalString: string): boolean => /^-?0(\.0{1,2})?$/.test(decimalString.trim());

/* ------------------------------------------------------- decimal strings ---- */

/** True for a decimal string an `Amount` can carry ("1250.50", "-3", "0.5"); never `Number()`. */
export function isDecimalString(v: unknown): v is string {
  return typeof v === 'string' && DECIMAL_RE.test(v.trim());
}

/**
 * True when the split parts add up exactly to the total (sign-insensitive, in centavos).
 * Client-side courtesy only — the API recomputes it and is the authority.
 */
export function splitsMatch(total: string, parts: string[]): boolean {
  if (!isDecimalString(total)) return false;
  if (parts.some((p) => !isDecimalString(p))) return false;
  const abs = (s: string) => s.trim().replace(/^-/, '');
  return sumDecimals([abs(total)]) === sumDecimals(parts.map(abs));
}
