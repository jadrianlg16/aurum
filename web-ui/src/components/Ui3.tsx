'use client';

/**
 * Shared pieces of the business, insights, reports and workflows screens: a tab strip, a
 * live-region toast, a copy-to-clipboard button, a horizontal bar chart for aging buckets
 * and a severity badge.
 *
 * Accessibility notes that are load-bearing here:
 *  - `Tabs` is a real `role="tablist"` with arrow-key navigation and roving tabindex;
 *  - `useToast` forwards to the app-wide ToastProvider, whose `aria-live="polite"` region exists
 *    from first paint, so a screen reader announces the message instead of missing the insertion;
 *  - `CopyButton` reports its result through that same live region.
 *
 * No money math: bar widths come from `toChartNumber`, which exists precisely so the one
 * float in the app is pixel geometry and never a displayed figure.
 */
import { useCallback, useMemo, useRef, type ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';
import { formatAmount, toChartNumber } from '@/lib/format';
import type { Amount, Severity } from '@/lib/types';
import { useToast as useUiToast } from './ui/Toast';

/* ------------------------------------------------------------------- tabs */

export interface TabSpec<T extends string> {
  id: T;
  label: string;
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: TabSpec<T>[];
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const move = (delta: number) => {
    const i = tabs.findIndex((tb) => tb.id === active);
    const next = tabs[(i + delta + tabs.length) % tabs.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  };

  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tb) => (
        <button
          key={tb.id}
          ref={(el) => {
            refs.current[tb.id] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${tb.id}`}
          aria-selected={tb.id === active}
          aria-controls={`panel-${tb.id}`}
          tabIndex={tb.id === active ? 0 : -1}
          className={tb.id === active ? 'active' : ''}
          onClick={() => onChange(tb.id)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') {
              e.preventDefault();
              move(1);
            } else if (e.key === 'ArrowLeft') {
              e.preventDefault();
              move(-1);
            }
          }}
        >
          {tb.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={-1}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ toast */

export interface Toaster {
  /** Announce a message; it clears itself after a few seconds. */
  show: (message: string) => void;
  /** Always `null`: the ToastProvider in layout.tsx owns the live regions. */
  node: ReactNode;
}

/**
 * Shim over `ui/useToast`: `show` forwards to the app-wide provider and
 * `node` is `null`, so the nine screens that render `{toast.node}` keep compiling and their
 * messages land in the one polite live region. The `Toaster` type is unchanged because
 * MoneySubs/MoneyCalendar take it as a prop.
 */
export function useToast(): Toaster {
  const api = useUiToast();
  const show = useCallback((m: string) => api.info(m), [api]);
  return useMemo(() => ({ show, node: null }), [show]);
}

/* ------------------------------------------------------------------- copy */

/**
 * Copy text to the clipboard. `navigator.clipboard` needs a secure context, which a plain
 * `http://localhost` build is — but a LAN `http://` origin is not, so the textarea fallback
 * stays: this app is meant to be self-hosted on whatever origin the user has.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the textarea path */
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({
  text,
  label,
  onDone,
  className = 'btn',
  disabled,
}: {
  text: string;
  label?: string;
  onDone?: (ok: boolean) => void;
  className?: string;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className={className}
      disabled={disabled}
      onClick={() => {
        void copyText(text).then((ok) => onDone?.(ok));
      }}
    >
      {label ?? t('common.copy')}
    </button>
  );
}

/* ------------------------------------------------------------------ chart */

/** A labelled horizontal bar per row — aging buckets, opex groups, top clients. */
export function BarRows({
  rows,
  emptyLabel,
}: {
  rows: { label: string; amount: Amount; note?: string }[];
  emptyLabel?: string;
}) {
  const { lang } = useI18n();
  if (rows.length === 0) return <p className="muted small">{emptyLabel ?? '—'}</p>;
  const max = Math.max(...rows.map((r) => Math.abs(toChartNumber(r.amount))), 0) || 1;
  return (
    <div className="barrows">
      {rows.map((r) => (
        <div className="barrow" key={r.label}>
          <span className="barrow-label">{r.label}</span>
          <span className="barrow-track" aria-hidden="true">
            <span
              className="barrow-fill"
              style={{ width: `${(Math.abs(toChartNumber(r.amount)) / max) * 100}%` }}
            />
          </span>
          <span className="barrow-value money">
            {formatAmount(r.amount, lang)}
            {r.note ? <span className="muted small"> · {r.note}</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- severity */

const SEVERITY_CLASS: Record<Severity, string> = {
  urgent: 'badge neg',
  warn: 'badge warn',
  info: 'badge info',
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { t } = useI18n();
  return <span className={SEVERITY_CLASS[severity]}>{t(`avisos.severity.${severity}`)}</span>;
}

/** `(verify)` is a literal marker the API embeds in strings; show it as a chip when present. */
export function verifyFlag(text: string | null | undefined): boolean {
  return Boolean(text && /\(verify\)/i.test(text));
}
