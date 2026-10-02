/**
 * Display formatting for wire values.
 *
 * Hard rule ("Money is Decimal", docs/ARCHITECTURE.md): money is a `str(Decimal)` on the wire
 * and never becomes a float for arithmetic. Every formatter here works on the digit string —
 * grouping, rounding and the sign are done on characters, so a long decimal is never rounded by
 * a binary float before it reaches the screen. The UI does no money math at all; totals come from the API.
 *
 * Money rules: the sign is always explicit (`−` U+2212 / `+`) and sits before the
 * currency affix; the workspace's base currency renders as `$`, a foreign one as `US$` / `MX$`
 * or its ISO code plus a space; `−0.00` collapses to `0.00`; nothing here throws — a value that
 * is not a decimal string comes back verbatim.
 *
 * Date rules: `todayLocalIso()` and `daysUntil()` use LOCAL calendar parts (never
 * `toISOString()`, which slips a day after 18:00 in Mexico City). Month and weekday names are
 * tables, not `Intl`: this app is a static export, and Node's CLDR data disagrees with the
 * browser's (`sept` vs `sep`), which React reports as a hydration mismatch. Nothing in this
 * file reads the clock unless the caller omits `today` — screens that prerender must pass it
 * from an effect (see docs/modules/design-system.md "no Date at prerender").
 */
import type { Amount, Lang } from './types';

const LOCALE: Record<Lang, string> = { es: 'es-MX', en: 'en-US' };

/** The currency each language treats as "home" when no workspace base is known. */
const HOME_CURRENCY: Record<Lang, string> = { es: 'MXN', en: 'USD' };

/** Short prefixes for the two currencies the product lives in; everything else is ISO + space. */
const PREFIX: Record<string, string> = { USD: 'US$', MXN: 'MX$' };

export const MINUS = '−';

const DECIMAL_RE = /^[+-]?\d+(\.\d+)?$/;

/* ----------------------------------------------------------------- digits */

/** Split "-1234.5600" into sign / integer digits / fraction digits, no float involved. */
function parts(decimal: string): { neg: boolean; int: string; frac: string } {
  const trimmed = (decimal ?? '0').trim();
  const neg = trimmed.startsWith('-');
  const body = trimmed.replace(/^[+-]/, '');
  const [int = '0', frac = ''] = body.split('.');
  return { neg, int: int || '0', frac };
}

/** Round half-up on the digit string itself, so no binary float ever touches the value. */
function roundDecimalString(decimal: string, places: number): { neg: boolean; digits: string } {
  const { neg, int, frac } = parts(decimal);
  if (frac.length <= places) {
    return { neg, digits: `${int}${frac.padEnd(places, '0')}` };
  }
  const keep = `${int}${frac.slice(0, places)}`;
  const next = frac.charCodeAt(places) - 48;
  if (next < 5) return { neg, digits: keep };
  const arr = keep.split('');
  let i = arr.length - 1;
  for (;;) {
    if (i < 0) {
      arr.unshift('1');
      break;
    }
    const d = arr[i].charCodeAt(0) - 48 + 1;
    if (d < 10) {
      arr[i] = String(d);
      break;
    }
    arr[i] = '0';
    i -= 1;
  }
  return { neg, digits: arr.join('') };
}

/** Group an integer digit string with the locale's separator (BigInt keeps it exact). */
function groupInt(intDigits: string, lang: Lang): string {
  const clean = intDigits.replace(/^0+(?=\d)/, '') || '0';
  try {
    return new Intl.NumberFormat(LOCALE[lang], { useGrouping: true }).format(BigInt(clean));
  } catch {
    return clean.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
}

function decimalSeparator(lang: Lang): string {
  try {
    return new Intl.NumberFormat(LOCALE[lang]).formatToParts(1.1).find((p) => p.type === 'decimal')?.value ?? '.';
  } catch {
    return '.';
  }
}

/* ------------------------------------------------------------------ money */

export interface MoneyOptions {
  /** The workspace's base currency: renders as a bare `$`. Defaults to the language's home. */
  base?: string | null;
  /** Drop the cents (home-screen headline figures). */
  compactCents?: boolean;
  /** `auto` shows `−` for negatives only; `always` also prefixes `+` on positives. */
  sign?: 'auto' | 'always';
  /** Render without the currency affix. */
  bare?: boolean;
}

/** Accepts the wire shape, a bare decimal string, or (defensively) a number. */
export type AmountLike = Amount | string | number | null | undefined;

function normalize(a: AmountLike, lang: Lang, base: string | null | undefined): { amount: string; currency: string } | null {
  if (a === null || a === undefined) return null;
  if (typeof a === 'string' || typeof a === 'number') {
    return { amount: String(a), currency: base ?? HOME_CURRENCY[lang] };
  }
  const raw = (a as { amount: unknown }).amount;
  if (raw === null || raw === undefined) return null;
  return { amount: String(raw), currency: (a.currency || base || HOME_CURRENCY[lang]).toUpperCase() };
}

/** The affix for a currency: `$` for the base, `US$`/`MX$` for the two home currencies, else ISO. */
export function currencyAffix(currency: string, base: string): { before: string; after: string } {
  const cur = currency.toUpperCase();
  if (cur === base.toUpperCase()) return { before: '$', after: '' };
  if (PREFIX[cur]) return { before: PREFIX[cur], after: '' };
  return { before: `${cur} `, after: '' };
}

/**
 * `{amount:'-1234.5', currency:'MXN'}` → `−$1,234.50` (base) / `−MX$1,234.50` (foreign).
 * Never throws: a value that is not a decimal string is returned as-is.
 */
export function formatAmount(a: AmountLike, lang: Lang, opts: MoneyOptions = {}): string {
  const n = normalize(a, lang, opts.base);
  if (!n) return '—';
  const trimmed = n.amount.trim();
  if (!DECIMAL_RE.test(trimmed)) return trimmed;

  const places = opts.compactCents ? 0 : 2;
  const rounded = roundDecimalString(trimmed, places);
  const allZero = /^0*$/.test(rounded.digits);
  const neg = rounded.neg && !allZero; // −0.00 collapses
  const intDigits = places === 0 ? rounded.digits : rounded.digits.slice(0, rounded.digits.length - places) || '0';
  const fracDigits = places === 0 ? '' : rounded.digits.slice(rounded.digits.length - places);

  const body = fracDigits ? `${groupInt(intDigits, lang)}${decimalSeparator(lang)}${fracDigits}` : groupInt(intDigits, lang);
  const sign = neg ? MINUS : opts.sign === 'always' && !allZero ? '+' : '';
  if (opts.bare) return `${sign}${body}`;

  const base = (opts.base ?? HOME_CURRENCY[lang]).toUpperCase();
  const { before, after } = currencyAffix(n.currency, base);
  return `${sign}${before}${body}${after}`;
}

/** Sign of a decimal string, without parsing it to a number. */
export function decimalSign(decimal: string | number | null | undefined): -1 | 0 | 1 {
  if (decimal === null || decimal === undefined) return 0;
  const s = String(decimal).trim();
  if (!DECIMAL_RE.test(s)) return 0;
  const { neg, int, frac } = parts(s);
  const zero = /^0*$/.test(int) && /^0*$/.test(frac);
  if (zero) return 0;
  return neg ? -1 : 1;
}

/** A ratio (0..1+) as a percentage. Ratios are plain numbers on the wire, not money. */
export function formatPct(v: number | string | null | undefined, lang: Lang, places = 0): string {
  const n = typeof v === 'string' ? Number(v) : v;
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  try {
    return new Intl.NumberFormat(LOCALE[lang], {
      style: 'percent',
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    }).format(n);
  } catch {
    return `${(n * 100).toFixed(places)}%`;
  }
}

/** A count or plain number (never money): grouped, optional fixed decimals. */
export function formatNumber(v: number | string | null | undefined, lang: Lang, places?: number): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'string' && DECIMAL_RE.test(v.trim())) {
    return formatAmount(v, lang, { bare: true, compactCents: places === 0 }).replace(MINUS, '-');
  }
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  try {
    return new Intl.NumberFormat(LOCALE[lang], {
      minimumFractionDigits: places ?? 0,
      maximumFractionDigits: places ?? 2,
    }).format(n);
  } catch {
    return String(n);
  }
}

/**
 * Charts need a numeric axis, and only there is a float acceptable: the value is used for
 * pixel geometry, never shown as a figure and never fed back into an API. Kept in one named
 * place so the money rule stays greppable.
 */
export function toChartNumber(a: Amount | null | undefined): number {
  if (!a) return 0;
  const n = Number(a.amount);
  return Number.isFinite(n) ? n : 0;
}

/* ------------------------------------------------------------------ dates */

const MONTH_ABBR: Record<Lang, string[]> = {
  es: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};
const MONTH_LONG: Record<Lang, string[]> = {
  es: [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
  ],
  en: [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ],
};
/** Index 0 = Sunday, as `Date#getDay()` returns it. */
const WEEKDAY_ABBR: Record<Lang, string[]> = {
  es: ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'],
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
};
const RELATIVE: Record<Lang, { today: string; tomorrow: string; yesterday: string; inDays: (n: number) => string; daysAgo: (n: number) => string }> = {
  es: {
    today: 'hoy',
    tomorrow: 'mañana',
    yesterday: 'ayer',
    inDays: (n) => `en ${n} ${n === 1 ? 'día' : 'días'}`,
    daysAgo: (n) => `hace ${n} ${n === 1 ? 'día' : 'días'}`,
  },
  en: {
    today: 'today',
    tomorrow: 'tomorrow',
    yesterday: 'yesterday',
    inDays: (n) => `in ${n} ${n === 1 ? 'day' : 'days'}`,
    daysAgo: (n) => `${n} ${n === 1 ? 'day' : 'days'} ago`,
  },
};

export type DateStyle = 'short' | 'medium' | 'long' | 'weekday';

/** `YYYY-MM-DD` → local calendar parts, or null when malformed. */
function isoParts(iso: string | null | undefined): { y: number; m: number; d: number } | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return { y, m: mo, d };
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** Local-time `YYYY-MM-DD` for a Date (default: now). Never `toISOString()`. */
export function todayLocalIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

function toLocalDate(v: string | Date): Date {
  if (v instanceof Date) return new Date(v.getFullYear(), v.getMonth(), v.getDate());
  const p = isoParts(v);
  return p ? new Date(p.y, p.m - 1, p.d) : new Date(NaN);
}

/** Whole days from `now` (local calendar day) to an ISO date; negative when past. */
export function daysUntil(iso: string, now: Date | string = new Date()): number {
  const target = toLocalDate(iso);
  const today = toLocalDate(now);
  if (Number.isNaN(target.getTime()) || Number.isNaN(today.getTime())) return 0;
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/**
 * `formatDate('2026-08-17', 'es')` → `17 ago 2026`; styles `short` (`17 ago`), `medium`
 * (default), `long` (`17 de agosto de 2026`), `weekday` (`lun 17 ago`). The legacy third
 * argument — an `Intl.DateTimeFormatOptions` object — still works for the advanced screens
 * (it goes through `Intl`, so it must not be used in anything that prerenders).
 */
export function formatDate(
  iso: string | null | undefined,
  lang: Lang,
  style: DateStyle | Intl.DateTimeFormatOptions = 'medium',
): string {
  if (!iso) return '—';
  const p = isoParts(iso);
  if (!p) return iso;
  if (typeof style === 'object') {
    const d = new Date(Date.UTC(p.y, p.m - 1, p.d));
    try {
      return new Intl.DateTimeFormat(LOCALE[lang], {
        timeZone: 'UTC',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        ...style,
      }).format(d);
    } catch {
      return iso;
    }
  }
  const mon = MONTH_ABBR[lang][p.m - 1];
  const long = MONTH_LONG[lang][p.m - 1];
  const wd = WEEKDAY_ABBR[lang][new Date(p.y, p.m - 1, p.d).getDay()];
  if (lang === 'es') {
    switch (style) {
      case 'short':
        return `${p.d} ${mon}`;
      case 'long':
        return `${p.d} de ${long} de ${p.y}`;
      case 'weekday':
        return `${wd} ${p.d} ${mon}`;
      default:
        return `${p.d} ${mon} ${p.y}`;
    }
  }
  switch (style) {
    case 'short':
      return `${mon} ${p.d}`;
    case 'long':
      return `${long} ${p.d}, ${p.y}`;
    case 'weekday':
      return `${wd}, ${mon} ${p.d}`;
    default:
      return `${mon} ${p.d}, ${p.y}`;
  }
}

/** `2026-09` → `sep 2026` (short) / `septiembre de 2026` (long). Table-driven, hydration-safe. */
export function formatPeriod(period: string, lang: Lang, style: 'short' | 'long' = 'short'): string {
  const m = Number(period.slice(5, 7));
  const y = period.slice(0, 4);
  const abbr = MONTH_ABBR[lang]?.[m - 1];
  const long = MONTH_LONG[lang]?.[m - 1];
  if (!abbr || !long || y.length !== 4) return period;
  if (style === 'long') return lang === 'es' ? `${long} de ${y}` : `${long} ${y}`;
  return `${abbr} ${y}`;
}

/**
 * `hoy` / `mañana` / `ayer` / `en 3 días` / `hace 2 días` inside ±7 days, else the medium date.
 * Pass `today` from an effect on prerendered screens.
 */
export function relativeDay(iso: string | null | undefined, lang: Lang, today: Date | string = new Date()): string {
  if (!iso) return '—';
  if (!isoParts(iso)) return iso;
  const n = daysUntil(iso, today);
  const r = RELATIVE[lang];
  if (n === 0) return r.today;
  if (n === 1) return r.tomorrow;
  if (n === -1) return r.yesterday;
  if (n > 1 && n <= 7) return r.inDays(n);
  if (n < -1 && n >= -7) return r.daysAgo(-n);
  return formatDate(iso, lang, 'medium');
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * A day group heading: `Hoy · vie 12 sep`, `Ayer · jue 11 sep`, `Mañana · sáb 13 sep`, else
 * `vie 12 sep` (with the year when it differs from today's).
 */
export function formatDayHeading(iso: string, lang: Lang, today: Date | string = new Date()): string {
  const p = isoParts(iso);
  if (!p) return iso;
  const n = daysUntil(iso, today);
  const t = toLocalDate(today);
  const sameYear = !Number.isNaN(t.getTime()) && t.getFullYear() === p.y;
  const base = sameYear ? formatDate(iso, lang, 'weekday') : `${formatDate(iso, lang, 'weekday')} ${p.y}`;
  const r = RELATIVE[lang];
  if (n === 0) return `${capitalize(r.today)} · ${base}`;
  if (n === 1) return `${capitalize(r.tomorrow)} · ${base}`;
  if (n === -1) return `${capitalize(r.yesterday)} · ${base}`;
  return base;
}
