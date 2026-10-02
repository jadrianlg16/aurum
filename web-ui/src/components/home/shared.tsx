'use client';

/**
 * Small helpers shared by the Home blocks. Nothing here touches the API and
 * nothing here sums money: `negate` flips a sign for display, `pctNumber` reads a percent (not
 * money), and `addDaysIso` does local calendar math.
 */
import { useId, type ReactNode } from 'react';
import type { Amount } from '@/lib/types';
import styles from './home.module.css';

/**
 * `'300.00'` → `'-300.00'` (and back). A string flip for display — the sign of a figure the
 * server sends positive but the screen must show as an outflow (signs are explicit). It
 * never parses the decimal; zero stays unsigned so `−0.00` never appears.
 */
export function negate(decimal: string): string {
  const s = decimal.trim();
  if (s === '' || /^[+-]?0*(\.0*)?$/.test(s)) return s.replace(/^[+-]/, '');
  return s.startsWith('-') ? s.slice(1) : `-${s.replace(/^\+/, '')}`;
}

export function negated(a: Amount): Amount {
  return { amount: negate(a.amount), currency: a.currency };
}

/** `'1500.0'` vs `'1500.00'` → equal. Compares decimal strings digit by digit, never as floats. */
export function sameDecimal(a: string, b: string): boolean {
  const norm = (v: string) => {
    const m = /^([+-]?)0*(\d*)(?:\.(\d*?)0*)?$/.exec(v.trim());
    if (!m) return v.trim();
    const int = m[2] || '0';
    const frac = m[3] ?? '';
    const zero = /^0*$/.test(int + frac);
    return `${zero ? '' : m[1] === '-' ? '-' : ''}${int}.${frac}`;
  };
  return norm(a) === norm(b);
}

/** `'2026-09-18'` + n days → local ISO (no `toISOString`). */
export function addDaysIso(iso: string, n: number): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** `pct` on the wire is a percent (number or str(Decimal)); a percent is not money. */
export function pctNumber(pct: number | string | null | undefined): number {
  const n = typeof pct === 'string' ? Number(pct) : pct;
  return n === null || n === undefined || Number.isNaN(n) ? 0 : n;
}

/** A native `<progress>` bar toned by budget state — no inline width, no hex. */
export function UsageBar({ pct, tone, label }: { pct: number; tone?: 'ok' | 'warn' | 'over' | null; label: string }) {
  const cls = [styles.bar, tone === 'warn' ? styles.warn : '', tone === 'over' ? styles.over : ''].filter(Boolean).join(' ');
  return <progress className={cls} value={Math.max(0, Math.min(100, pct))} max={100} aria-label={label} />;
}

/** A labelled `.card` section: heading + optional trailing actions, then the body. */
export function HomeSection({
  title,
  actions,
  children,
  className,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section className={['card', className].filter(Boolean).join(' ')} aria-labelledby={id}>
      <div className={styles.head}>
        <h2 id={id}>{title}</h2>
        {actions && <span className={styles.headActions}>{actions}</span>}
      </div>
      {children}
    </section>
  );
}
