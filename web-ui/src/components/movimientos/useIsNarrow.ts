'use client';

/**
 * `true` below 768px (`matchMedia('(max-width: 767px)')`), the breakpoint where
 * `ResponsiveTable` switches to cards and Movimientos moves its filters into a Sheet.
 * Starts `false` so the prerendered markup matches the server; the real value lands after
 * mount and follows the media query from then on.
 */
import { useSyncExternalStore } from 'react';

const QUERY = '(max-width: 767px)';

function subscribe(onChange: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {};
  const mql = window.matchMedia(QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

function snapshot(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(QUERY).matches;
}

export function useIsNarrow(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
