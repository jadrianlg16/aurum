'use client';

/**
 * Display primitives: Money, Badge, Stat, Sparkline,
 * MonthPicker, Tabs, PageHeader, ThemeToggle.
 *
 * Money: the sign is always explicit (`−` U+2212 / `+`) and never colour-only — an sr-only
 * "entrada"/"salida" precedes the figure whenever a sign is shown. The base currency renders
 * `$`, a foreign one `US$`/`MX$`/ISO (via `useMoney()`).
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { usePageTitle } from '@/lib/a11y';
import { decimalSign, formatAmount, formatPeriod, toChartNumber, MINUS, type AmountLike } from '@/lib/format';
import { useI18n, useMoney } from '@/lib/i18n';
import { replaceQueryParam } from '@/lib/query';
import { useTheme, type Theme } from '@/lib/theme';
import type { Amount, Explain as ExplainModel } from '@/lib/types';
import { Explain } from '../Explain';
import { Button } from './Button';
import { Icon } from './Icon';

/* ------------------------------------------------------------------ Money */

export type MoneyTone = 'auto' | 'pos' | 'neg' | 'neutral' | 'none';

export interface MoneyProps {
  amount: AmountLike;
  /** Only used when `amount` is a bare string. */
  currency?: string;
  sign?: 'auto' | 'always';
  compactCents?: boolean;
  /** `auto` colours by sign; `none` (default) leaves the text colour alone. */
  tone?: MoneyTone;
  className?: string;
}

export function Money({ amount, currency, sign = 'auto', compactCents, tone = 'none', className }: MoneyProps) {
  const { t } = useI18n();
  const { fmt, base } = useMoney();
  const value: AmountLike =
    typeof amount === 'string' || typeof amount === 'number' ? { amount: String(amount), currency: currency ?? base } : amount;
  const text = fmt(value, { sign, compactCents });
  const s = value && typeof value === 'object' ? decimalSign(value.amount) : 0;
  const showsSign = text.startsWith(MINUS) || text.startsWith('+');
  const toneCls = tone === 'auto' ? (s > 0 ? 'pos' : s < 0 ? 'neg' : '') : tone === 'none' ? '' : tone;
  return (
    <span className={['money', toneCls, className].filter(Boolean).join(' ')}>
      {showsSign && <span className="sr-only">{s < 0 ? t('a11y.amount_negative') : t('a11y.amount_positive')} </span>}
      {text}
    </span>
  );
}

/* ------------------------------------------------------------------ Badge */

export type BadgeTone = 'neutral' | 'accent' | 'pos' | 'neg' | 'warn' | 'info';

export function Badge({ tone = 'neutral', dot, children, className }: { tone?: BadgeTone; dot?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={['badge', tone, className].filter(Boolean).join(' ')}>
      {dot && <span className="badge-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------- Stat */

export interface StatProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  /** Change versus a reference: `{amount, vs}` → `+$120.00 vs. mes anterior`. */
  delta?: { amount: Amount; vs: string };
  tone?: 'pos' | 'neg' | 'warn' | 'neutral';
  explain?: ExplainModel | null;
  size?: 'md' | 'lg';
  className?: string;
}

export function Stat({ label, value, sub, delta, tone, explain, size = 'md', className }: StatProps) {
  return (
    <div className={['ui-stat', size, tone && tone !== 'neutral' ? tone : '', className].filter(Boolean).join(' ')}>
      <span className="ui-stat-label">{label}</span>
      <span className="ui-stat-value">{value}</span>
      {sub && <span className="ui-stat-sub">{sub}</span>}
      {delta && (
        <span className="ui-stat-delta">
          <Money amount={delta.amount} sign="always" tone="auto" /> {delta.vs}
        </span>
      )}
      {explain && <Explain explain={explain} quiet />}
    </div>
  );
}

/* -------------------------------------------------------------- Sparkline */

export interface SparklineProps {
  points: { label: string; value: Amount }[];
  /** Accessible name; defaults to the labelled values. */
  title?: string;
  height?: number;
  columns?: boolean;
  className?: string;
}

/**
 * A sparkline / column chart over a money series. The only place a float touches an amount:
 * `toChartNumber` produces pixel geometry, never a displayed figure. Drawn in `currentColor`
 * so it follows the theme.
 */
export function Sparkline({ points, title, height = 56, columns = false, className }: SparklineProps) {
  const { lang } = useI18n();
  const id = useId();
  if (points.length === 0) return null;
  const nums = points.map((p) => toChartNumber(p.value));
  const max = Math.max(...nums, 0);
  const min = Math.min(...nums, 0);
  const span = max - min || 1;
  const w = 100;
  const h = height;
  const x = (i: number) => (points.length === 1 ? w / 2 : (i / (points.length - 1)) * w);
  const y = (v: number) => h - ((v - min) / span) * (h - 8) - 4;
  const zeroY = y(0);
  const name = title ?? points.map((p) => `${p.label}: ${formatAmount(p.value, lang)}`).join('; ');

  return (
    <svg
      className={['sparkline', className].filter(Boolean).join(' ')}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-labelledby={id}
      style={{ color: 'var(--accent)' }}
    >
      <title id={id}>{name}</title>
      {min < 0 && <line x1={0} x2={w} y1={zeroY} y2={zeroY} stroke="var(--line-strong)" strokeWidth={0.5} />}
      {columns ? (
        points.map((p, i) => {
          const v = nums[i];
          const top = Math.min(y(v), zeroY);
          const barH = Math.max(1, Math.abs(zeroY - y(v)));
          const bw = w / points.length - 1.5;
          return (
            <rect
              key={`${p.label}-${i}`}
              x={(i * w) / points.length + 0.75}
              y={top}
              width={bw}
              height={barH}
              fill={v < 0 ? 'var(--neg)' : 'currentColor'}
              rx={0.8}
            >
              <title>{`${p.label}: ${formatAmount(p.value, lang)}`}</title>
            </rect>
          );
        })
      ) : (
        <>
          <polyline
            points={points.map((_, i) => `${x(i)},${y(nums[i])}`).join(' ')}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            vectorEffect="non-scaling-stroke"
          />
          <circle cx={x(points.length - 1)} cy={y(nums[nums.length - 1])} r={1.8} fill="currentColor" />
        </>
      )}
    </svg>
  );
}

/* ------------------------------------------------------------ MonthPicker */

function shiftMonth(period: string, delta: number): string {
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(5, 7)) - 1 + delta;
  const yy = y + Math.floor(m / 12);
  const mm = ((m % 12) + 12) % 12;
  return `${yy}-${String(mm + 1).padStart(2, '0')}`;
}

export interface MonthPickerProps {
  value: string;
  onChange: (period: string) => void;
  min?: string;
  max?: string;
  className?: string;
}

/** ‹ › + Hoy; ←/→ while focused; the label is announced politely and formatted after mount. */
export function MonthPicker({ value, onChange, min, max, className }: MonthPickerProps) {
  const { t, lang } = useI18n();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const canPrev = !min || shiftMonth(value, -1) >= min;
  const canNext = !max || shiftMonth(value, 1) <= max;
  const go = (delta: number) => {
    if (delta < 0 && !canPrev) return;
    if (delta > 0 && !canNext) return;
    onChange(shiftMonth(value, delta));
  };
  const today = () => {
    const d = new Date();
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      go(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      go(1);
    }
  };
  return (
    // Arrow keys work when any of the three buttons inside has focus (they bubble here).
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div className={['ui-month', className].filter(Boolean).join(' ')} role="group" aria-label={t('a11y.month_nav')} onKeyDown={onKey}>
      <Button size="sm" variant="ghost" icon="chevron-left" aria-label={t('a11y.month_prev')} onClick={() => go(-1)} disabled={!canPrev} />
      <span className="ui-month-label" aria-live="polite">
        {mounted ? formatPeriod(value, lang, 'short') : value}
      </span>
      <Button size="sm" variant="ghost" icon="chevron-right" aria-label={t('a11y.month_next')} onClick={() => go(1)} disabled={!canNext} />
      <Button size="sm" variant="ghost" onClick={today}>
        {t('form.today')}
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------- Tabs */

export interface TabItem<T extends string = string> {
  id: T;
  label: string;
  count?: number;
}

export interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  /** Mirror the active tab into `?<queryKey>=` (history.replaceState). */
  queryKey?: string;
  label: string;
  className?: string;
}

/** Scrollable pills with a real tablist: roving tabindex, ←/→/Home/End. */
export function Tabs<T extends string>({ items, value, onChange, queryKey, label, className }: TabsProps<T>) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const pick = (id: T, focus = false) => {
    onChange(id);
    if (queryKey) replaceQueryParam(queryKey, id);
    if (focus) refs.current[id]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = items.findIndex((it) => it.id === value);
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % items.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + items.length) % items.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    if (next < 0) return;
    e.preventDefault();
    pick(items[next].id, true);
  };
  return (
    <div className={['ui-tabs', className].filter(Boolean).join(' ')} role="tablist" aria-label={label}>
      {items.map((it) => (
        <button
          key={it.id}
          ref={(el) => {
            refs.current[it.id] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${it.id}`}
          aria-selected={it.id === value}
          aria-controls={`panel-${it.id}`}
          tabIndex={it.id === value ? 0 : -1}
          onClick={() => pick(it.id)}
          onKeyDown={onKey}
        >
          {it.label}
          {typeof it.count === 'number' && <span className="ui-tab-count">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children, className }: { id: string; children: ReactNode; className?: string }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={-1} className={className}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------- PageHeader */

export interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Renders a MonthPicker next to the actions. */
  month?: MonthPickerProps;
  className?: string;
}

/** The page's only `<h1>`; also sets `document.title` to `'<title> · Aurum'`. */
export function PageHeader({ title, subtitle, actions, month, className }: PageHeaderProps) {
  usePageTitle(title);
  return (
    <header className={['ui-pagehead', className].filter(Boolean).join(' ')}>
      <div className="ui-pagehead-title">
        <h1>{title}</h1>
        {subtitle && <p className="ui-pagehead-sub">{subtitle}</p>}
      </div>
      {(month || actions) && (
        <div className="ui-pagehead-actions">
          {month && <MonthPicker {...month} />}
          {actions}
        </div>
      )}
    </header>
  );
}

/* ------------------------------------------------------------ ThemeToggle */

const THEMES: { id: Theme; icon: 'sun' | 'moon' | 'settings' }[] = [
  { id: 'system', icon: 'settings' },
  { id: 'light', icon: 'sun' },
  { id: 'dark', icon: 'moon' },
];

/** Sistema / Claro / Oscuro as a pressed-button group. */
export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useI18n();
  const { theme, setTheme } = useTheme();
  return (
    <div className={['ui-chips', className].filter(Boolean).join(' ')} role="group" aria-label={t('header.theme')}>
      {THEMES.map((th) => (
        <button key={th.id} type="button" className="ui-chip" aria-pressed={theme === th.id} onClick={() => setTheme(th.id)}>
          <Icon name={th.icon} size={14} /> {t(`theme.${th.id}`)}
        </button>
      ))}
    </div>
  );
}
