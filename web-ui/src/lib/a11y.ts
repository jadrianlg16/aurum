'use client';

/**
 * Accessibility helpers shared by the shell and the ui primitives.
 *
 * - `useReturnFocus(active)` remembers the element that had focus when `active` flipped true
 *   and gives it back when it flips false (dialogs, sheets).
 * - `useShortcut(key, handler, {when})` binds one plain key (no modifiers, no chords) that is
 *   ignored while the user is typing or while any native dialog is open.
 * - `usePageTitle(title)` sets `document.title` to `'<title> · Aurum'` for the page's lifetime.
 */
import { useEffect, useRef, useSyncExternalStore } from 'react';

const APP_NAME = 'Aurum';

/** True when the keyboard event started inside something that takes text. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement ||
    (el.isContentEditable ?? false)
  );
}

/** True while a native `<dialog open>` is on screen — shortcuts must not fire behind it. */
export function dialogIsOpen(): boolean {
  return typeof document !== 'undefined' && document.querySelector('dialog[open]') !== null;
}

/**
 * When `active` becomes true, remember `document.activeElement`; when it becomes false again,
 * focus it. The remembered element is only refocused if it is still connected.
 */
export function useReturnFocus(active: boolean): void {
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (active) {
      opener.current = (document.activeElement as HTMLElement | null) ?? null;
      return () => {
        const el = opener.current;
        opener.current = null;
        if (el && el.isConnected && typeof el.focus === 'function') {
          // After the dialog's own close() has run, so the top layer is gone.
          el.focus({ preventScroll: true });
        }
      };
    }
    return undefined;
  }, [active]);
}

export interface ShortcutOptions {
  /** Only bind while true (e.g. advanced mode). Defaults to true. */
  when?: boolean;
  /** Let the shortcut fire even when a dialog is open (Esc handlers). */
  allowInDialog?: boolean;
}

/**
 * One key, no modifiers. Ignored while typing, while a `dialog[open]` exists (unless
 * `allowInDialog`), and when `when` is false. `handler` is read through a ref so callers can
 * pass a fresh closure every render without rebinding.
 */
export function useShortcut(key: string, handler: (e: KeyboardEvent) => void, opts: ShortcutOptions = {}): void {
  const { when = true, allowInDialog = false } = opts;
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!when) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== key || e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      if (isTypingTarget(e.target)) return;
      if (!allowInDialog && dialogIsOpen()) return;
      ref.current(e);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [key, when, allowInDialog]);
}

/** Compose the document title the same way everywhere. */
export function pageTitle(title: string | null | undefined): string {
  const t = (title ?? '').trim();
  return t ? `${t} · ${APP_NAME}` : APP_NAME;
}

/*
 * Page title store. React 19 hoists a `<title>` rendered anywhere in the tree into `<head>`,
 * and the Shell renders exactly one — so the title is React state, not a `document.title`
 * write that Next's metadata commit would overwrite a few ms later. `usePageTitle(title)`
 * registers a claim; the most recent mounted claim wins; with no claim the Shell falls back to
 * the active nav item.
 */
const claims = new Map<number, string>();
const listeners = new Set<() => void>();
let claimSeq = 0;
let snapshot: string | null = null;

function recompute() {
  let latest: string | null = null;
  for (const v of claims.values()) latest = v;
  snapshot = latest;
  for (const l of listeners) l();
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function hasPageTitleClaim(): boolean {
  return claims.size > 0;
}

/** The title a page claimed with `usePageTitle`, or null (Shell falls back to the nav item). */
export function useClaimedTitle(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => null,
  );
}

/** Claim the page title (`<title> · Aurum`) while mounted; the Shell renders it. */
export function usePageTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (!title) return undefined;
    const id = ++claimSeq;
    claims.set(id, title);
    recompute();
    return () => {
      claims.delete(id);
      recompute();
    };
  }, [title]);
}

/** Move keyboard focus to `<main id="main">` (after rail navigation, after the skip link). */
export function focusMain(): void {
  const main = document.getElementById('main');
  if (main) main.focus({ preventScroll: false });
}
