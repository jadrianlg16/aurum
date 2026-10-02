'use client';

/**
 * API health, read once for the whole app (and again on `refresh()`).
 *
 * What the UI *acts* on:
 *   - `demoMode` (`AURUM_DEMO_MODE=1`): the API is read-only, so every write button is
 *     disabled and says why rather than firing a request the API will reject;
 *   - `authRequired` (`health.auth.required`, or the legacy `auth_required`):
 *     the API wants a bearer token — Ajustes › Avanzado (Token de la API) is where it is typed;
 *   - `unauthorized`: some request answered 401 with the token we have (or none). Set by the
 *     `onUnauthorized` registry in lib/api.ts (at most once per 2 s) and cleared by the first
 *     2xx afterwards (`onRequestOk`), so the Shell banner follows reality without polling.
 *
 * Every flag is optional on the wire and its absence means "no", never "unknown".
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getHealth, onRequestOk, onUnauthorized } from './api';
import type { Health } from './types';

interface HealthValue {
  health: Health | null;
  demoMode: boolean;
  /** True while the first /health call is in flight. */
  loading: boolean;
  authRequired: boolean;
  unauthorized: boolean;
  /** Re-read /health (after the token is saved in Ajustes). */
  refresh: () => void;
}

const HealthContext = createContext<HealthValue>({
  health: null,
  demoMode: false,
  loading: true,
  authRequired: false,
  unauthorized: false,
  refresh: () => {},
});

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    getHealth()
      .then((h) => {
        if (alive) setHealth(h);
      })
      .catch(() => {
        // A dead or unauthorized API must not blank the shell; screens show their own errors
        // (a 401 here is reported through the registry below).
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [nonce]);

  useEffect(() => {
    const offUnauthorized = onUnauthorized(() => setUnauthorized(true));
    const offOk = onRequestOk(() => setUnauthorized(false));
    return () => {
      offUnauthorized();
      offOk();
    };
  }, []);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const value = useMemo<HealthValue>(
    () => ({
      health,
      demoMode: health?.demo_mode === true,
      loading,
      authRequired: health?.auth?.required === true || health?.auth_required === true,
      unauthorized,
      refresh,
    }),
    [health, loading, unauthorized, refresh],
  );
  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}

export function useHealth(): HealthValue {
  return useContext(HealthContext);
}

/**
 * Props for a button that writes: disabled with an explanation while the API is read-only.
 * Used as `<button {...writeGuard(demoMode, t('settings.demo.tooltip'))}>`.
 */
export function writeGuard(demoMode: boolean, tooltip: string) {
  return demoMode ? { disabled: true, title: tooltip, 'aria-disabled': true as const } : {};
}
