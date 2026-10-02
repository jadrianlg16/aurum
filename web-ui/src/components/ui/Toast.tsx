'use client';

/**
 * Toasts.
 *
 * One `role="status" aria-live="polite"` region and one `role="alert" aria-live="assertive"`
 * region are always in the DOM, so assistive tech announces changes instead of missing the
 * insertion. `useToast()` gives `success(msg, {action})`, `error(msg)` and `info(msg)`; at most
 * three are visible, they auto-dismiss after 5 s (8 s for errors), pause while hovered or
 * focused, carry an optional action (Deshacer) and a Cerrar button, and Esc dismisses the
 * newest. Bottom-right on wide screens, above the tab bar on narrow ones (globals.css).
 *
 * A toast requested while a native `<dialog>` is open is held until the dialog closes — the
 * top layer would otherwise cover it.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { dialogIsOpen } from '@/lib/a11y';
import { useI18n } from '@/lib/i18n';
import { Icon } from './Icon';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  action?: ToastAction;
  /** ms; 5000 for success/info, 8000 for error. */
  duration: number;
}

export interface ToastApi {
  success: (message: string, opts?: { action?: ToastAction }) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  dismiss: (id: number) => void;
}

const MAX_VISIBLE = 3;
const DURATION: Record<ToastKind, number> = { success: 5000, info: 5000, error: 8000 };

const ToastContext = createContext<ToastApi | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [items, setItems] = useState<ToastItem[]>([]);
  const pending = useRef<ToastItem[]>([]);
  const paused = useRef(false);

  const flush = useCallback(() => {
    if (pending.current.length === 0 || dialogIsOpen()) return;
    const batch = pending.current;
    pending.current = [];
    setItems((cur) => [...cur, ...batch].slice(-MAX_VISIBLE));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string, action?: ToastAction) => {
      const item: ToastItem = { id: nextId++, kind, message, action, duration: DURATION[kind] };
      pending.current.push(item);
      flush();
    },
    [flush],
  );

  // Deferred toasts: a dialog's `close` event does not bubble to the window, so the queue is
  // re-checked on a cheap timer while something is pending.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (pending.current.length > 0) flush();
    }, 150);
    return () => window.clearInterval(id);
  }, [flush]);

  const dismiss = useCallback((id: number) => {
    setItems((cur) => cur.filter((x) => x.id !== id));
  }, []);

  // Esc dismisses the newest toast (only when no dialog is open — the dialog owns Esc there).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || dialogIsOpen()) return;
      setItems((cur) => (cur.length ? cur.slice(0, -1) : cur));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (message, opts) => push('success', message, opts?.action),
      error: (message) => push('error', message),
      info: (message) => push('info', message),
      dismiss,
    }),
    [push, dismiss],
  );

  const polite = items.filter((x) => x.kind !== 'error');
  const assertive = items.filter((x) => x.kind === 'error');

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="ui-toasts"
        onMouseEnter={() => {
          paused.current = true;
        }}
        onMouseLeave={() => {
          paused.current = false;
        }}
        onFocus={() => {
          paused.current = true;
        }}
        onBlur={() => {
          paused.current = false;
        }}
      >
        <div role="status" aria-live="polite" aria-atomic="true" aria-label={t('a11y.notifications')}>
          {polite.map((item) => (
            <ToastView key={item.id} item={item} paused={paused} onDismiss={dismiss} closeLabel={t('a11y.close')} />
          ))}
        </div>
        <div role="alert" aria-live="assertive" aria-atomic="true" aria-label={t('a11y.errors')}>
          {assertive.map((item) => (
            <ToastView key={item.id} item={item} paused={paused} onDismiss={dismiss} closeLabel={t('a11y.close')} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({
  item,
  paused,
  onDismiss,
  closeLabel,
}: {
  item: ToastItem;
  paused: { current: boolean };
  onDismiss: (id: number) => void;
  closeLabel: string;
}) {
  // A ticking timer that only counts while not paused, so hover/focus really holds the toast.
  useEffect(() => {
    let left = item.duration;
    const tick = window.setInterval(() => {
      if (paused.current) return;
      left -= 250;
      if (left <= 0) {
        window.clearInterval(tick);
        onDismiss(item.id);
      }
    }, 250);
    return () => window.clearInterval(tick);
  }, [item, paused, onDismiss]);

  return (
    <div className={`ui-toast ${item.kind}`}>
      <span className="ui-toast-msg">{item.message}</span>
      {item.action && (
        <button
          type="button"
          className="ui-toast-action"
          onClick={() => {
            item.action?.onClick();
            onDismiss(item.id);
          }}
        >
          {item.action.label}
        </button>
      )}
      <button type="button" className="ui-toast-close" aria-label={closeLabel} onClick={() => onDismiss(item.id)}>
        <Icon name="x" size={16} />
      </button>
    </div>
  );
}

const NOOP: ToastApi = { success: () => {}, error: () => {}, info: () => {}, dismiss: () => {} };

/** Toast API. Outside a provider (never in this app) it is a no-op rather than a crash. */
export function useToast(): ToastApi {
  return useContext(ToastContext) ?? NOOP;
}
