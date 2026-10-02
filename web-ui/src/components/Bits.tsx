'use client';

/**
 * Small shared presentational pieces. No data fetching, no money math.
 *
 * `Money`, `Loading`, `ErrorBox`, `Empty` and `Sparkline` are shims over `components/ui` so
 * the ~30 older importers (the advanced screens) keep compiling; new screens import the
 * primitives directly.
 */
import type { ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';
import { formatPct } from '@/lib/format';
import type { Amount, Explain as ExplainModel } from '@/lib/types';
import { Explain } from './Explain';
import { Money as UiMoney } from './ui/Display';
import { EmptyState, ErrorBox as UiErrorBox, Skeleton } from './ui/Feedback';

/**
 * Money — a shim over `ui/Money`: the sign is always explicit now, so the
 * legacy `sign` flag only decides whether the figure is coloured by direction.
 */
export function Money({
  value,
  sign = false,
  compactCents = false,
  className = '',
}: {
  value: Amount | null | undefined;
  sign?: boolean;
  compactCents?: boolean;
  className?: string;
}) {
  return <UiMoney amount={value} compactCents={compactCents} tone={sign ? 'auto' : 'none'} className={className} />;
}

/** A headline figure with its label and, optionally, the Explain that produced it. */
export function Metric({
  label,
  value,
  sub,
  explain,
  children,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  explain?: ExplainModel | null;
  children?: ReactNode;
}) {
  return (
    <div className="card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="small muted" style={{ marginTop: 4 }}>{sub}</div>}
      {children}
      {explain && <Explain explain={explain} />}
    </div>
  );
}

export function Section({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>{title}</h2>
        <div className="spacer" style={{ flex: 1 }} />
        {actions}
      </div>
      {children}
    </section>
  );
}

/** Shim: the first-load skeleton. Reloads should keep content and set `refreshing`. */
export function Loading() {
  return <Skeleton variant="text" rows={3} />;
}

/** Shim over `ui/ErrorBox` — the ~30 older callers pass a plain message string. */
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <UiErrorBox error={message} onRetry={onRetry} />;
}

/** Shim over `ui/EmptyState` in compact form. */
export function Empty({ text }: { text?: string }) {
  const { t } = useI18n();
  return <EmptyState compact title={text ?? t('common.empty')} />;
}

/** A progress bar for a ratio the API computed. `pct` is a plain number, never money. */
export function ProgressBar({ pct, tone }: { pct: number; tone?: 'pos' | 'warn' | 'neg' }) {
  const width = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div className={`bar ${tone ?? ''}`}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

export function Pct({ value, places = 0 }: { value: number; places?: number }) {
  const { lang } = useI18n();
  return <span className="money">{formatPct(value, lang, places)}</span>;
}

/** Re-export of `ui/Sparkline` (same `points/height/columns` props; `title` optional). */
export { Sparkline } from './ui/Display';
