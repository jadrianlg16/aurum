/**
 * Deep links into a static export.
 *
 * The export has no dynamic route segments, so the workspace and the open tab live in the
 * query string when someone wants to link straight at a screen: `/plan/?tab=holdings`,
 * `/taxes/?ws=demo-us`. Nothing is *stored* from the query — it only seeds the first render,
 * after which the normal in-app state (and localStorage, for the workspace) takes over.
 *
 * Safe on the server: during prerender there is no `window`, so every reader returns null.
 */
import { useEffect, useState } from 'react';

export function queryParam(name: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return new URLSearchParams(window.location.search).get(name);
  } catch {
    return null;
  }
}

/** The `?tab=` value, but only when it is one this screen actually has. */
export function queryTab<T extends string>(valid: readonly T[]): T | null {
  const v = queryParam('tab');
  return v && (valid as readonly string[]).includes(v) ? (v as T) : null;
}

/** Sets (or clears) one query-string param on the current URL without a navigation. */
export function replaceQueryParam(name: string, value: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    if (value == null) url.searchParams.delete(name);
    else url.searchParams.set(name, value);
    window.history.replaceState(window.history.state, '', url.toString());
  } catch {
    /* ignore */
  }
}

/**
 * Tab state for a screen whose open tab is deep-linkable via `?tab=`.
 *
 * The state itself always **starts at `initial`** — the same value the server rendered, since
 * prerendering has no `window` to read a query string from. Reading `?tab=` in the `useState`
 * initializer instead would make the very first client render disagree with the server-rendered
 * markup (server: default tab; client: the `?tab=` one) for a subtree that switches both a
 * component and an id by tab — exactly the kind of structural mismatch React's hydration does
 * not reliably repair, so the tab bar can end up highlighting the default tab forever while the
 * right panel's content renders underneath it. Applying `?tab=` from an effect instead means the
 * first paint always matches the server (no mismatch to recover from), and the switch to the
 * deep-linked tab then happens as an ordinary client re-render right after mount.
 *
 * Picking a tab keeps the URL in sync via `history.replaceState` (no navigation), so the address
 * bar, a bookmark, or a screenshot script always reflects the tab actually on screen.
 */
export function useQueryTab<T extends string>(valid: readonly T[], initial: T): [T, (next: T) => void] {
  const [tab, setTabState] = useState<T>(initial);

  useEffect(() => {
    const wanted = queryTab(valid);
    if (wanted && wanted !== initial) setTabState(wanted);
    // Only ever applied once, right after mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setTab = (next: T) => {
    setTabState(next);
    replaceQueryParam('tab', next);
  };

  return [tab, setTab];
}

/* ------------------------------------------------------------- aliases ---- */

/** `queryParam` under its older name. */
export const readQuery = queryParam;

/** `replaceQueryParam` under its older name: set (or clear with `null`) one param, no navigation. */
export const writeQuery = replaceQueryParam;

/**
 * Generic deep-linkable state for `?tab=` / `?step=` / `?period=`: starts at `initial` (what
 * the server rendered), applies the URL value once after mount when `valid` accepts it, and
 * writes back through `replaceState`. `valid` is a list of allowed values or a predicate.
 */
export function useQueryParam<T extends string>(
  name: string,
  initial: T,
  valid?: readonly T[] | ((v: string) => boolean),
): [T, (next: T) => void] {
  const [value, setValueState] = useState<T>(initial);

  useEffect(() => {
    const raw = queryParam(name);
    if (raw === null || raw === initial) return;
    const ok =
      valid === undefined ? true : typeof valid === 'function' ? valid(raw) : (valid as readonly string[]).includes(raw);
    if (ok) setValueState(raw as T);
    // Only ever applied once, right after mount (see useQueryTab).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setValue = (next: T) => {
    setValueState(next);
    replaceQueryParam(name, next);
  };

  return [value, setValue];
}
