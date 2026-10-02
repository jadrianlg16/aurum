'use client';

/**
 * One tiny data hook for the whole app: run an async loader, expose `{data, error, loading,
 * refreshing}` and a `reload`. No data-fetching library — a local single-user app loads once
 * on mount and reloads on an explicit user action.
 *
 * Stale-while-refresh:
 *   - `loading` is true only for the FIRST load; later loads flip `refreshing` and keep the
 *     previous `data` on screen (`keepPrevious`, default true) — never a swap to "Cargando…";
 *   - every run gets an `AbortController`; deps change or unmount aborts the in-flight one,
 *     and an aborted result never lands;
 *   - inside `<WorkspaceProvider>` nothing fires while the workspace is unresolved, and
 *     `data` resets when the resolved id changes;
 *   - `error` is human copy via `errorMessage(e, t)` in the UI language; `problem` is the raw
 *     thrown value for callers that branch on `ApiError.code`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage } from './api';
import { useI18n } from './i18n';
import { useMaybeWorkspace } from './workspace';

export interface Resource<T> {
  data: T | null;
  /** Localized message, or null. */
  error: string | null;
  /** The raw thrown value (an `ApiError` for HTTP failures). */
  problem: unknown;
  /** True during the first load only (render a Skeleton). */
  loading: boolean;
  /** True while a later load runs with the previous data still shown. */
  refreshing: boolean;
  reload: () => void;
  /** Optimistic local update (used by the Inbox after accept/reject). */
  set: (updater: (prev: T | null) => T | null) => void;
}

export interface ResourceOptions {
  /** Keep `data` on screen while reloading (default). `false` clears it and shows `loading`. */
  keepPrevious?: boolean;
}

/** The translator when the hook runs inside `<I18nProvider>`, else undefined (Spanish table). */
function useMaybeT(): ((key: never, vars?: Record<string, string | number>) => string) | undefined {
  try {
    // useContext under the hood — the throw only happens outside the provider.
    return useI18n().t as (key: never) => string;
  } catch {
    return undefined;
  }
}

export function useResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  opts: ResourceOptions = {},
): Resource<T> {
  const keepPrevious = opts.keepPrevious ?? true;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const loadedOnce = useRef(false);
  const lastWs = useRef<string | null | undefined>(undefined);
  const t = useMaybeT();
  const tRef = useRef(t);
  tRef.current = t;

  const wsCtx = useMaybeWorkspace();
  // Outside the provider the hook is not gated; inside, null means "not resolved yet".
  const wsOrNull = wsCtx ? wsCtx.wsOrNull : 'ungated';

  useEffect(() => {
    if (wsOrNull === null) {
      // No request until the workspace is resolved. Stay in the first-load state.
      setLoading(true);
      return;
    }
    if (lastWs.current !== undefined && lastWs.current !== wsOrNull) {
      // The resolved workspace changed: yesterday's rows must not flash under today's id.
      loadedOnce.current = false;
      setData(null);
    }
    lastWs.current = wsOrNull;

    const controller = new AbortController();
    const first = !loadedOnce.current || !keepPrevious;
    if (first) {
      setLoading(true);
      if (!keepPrevious) setData(null);
    } else {
      setRefreshing(true);
    }
    setError(null);
    setProblem(null);

    loaderRef
      .current(controller.signal)
      .then((d) => {
        if (controller.signal.aborted) return;
        loadedOnce.current = true;
        setData(d);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        if (e instanceof Error && e.name === 'AbortError') return;
        setProblem(e);
        setError(errorMessage(e, tRef.current));
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        setLoading(false);
        setRefreshing(false);
      });
    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, wsOrNull, keepPrevious]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const set = useCallback((updater: (prev: T | null) => T | null) => setData(updater), []);

  return { data, error, problem, loading, refreshing, reload, set };
}
