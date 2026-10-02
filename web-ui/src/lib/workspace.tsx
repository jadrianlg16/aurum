'use client';

/**
 * Current-workspace context.
 *
 * Every screen reads `ws` from here rather than from the URL, because a static export has no
 * dynamic route segments and nearly every endpoint carries the workspace id in its *path*.
 *
 * Resolution order, once, before the first data request:
 *   1. `?ws=` (validated, persisted to `aurum.ws`, stripped from the URL via replaceState);
 *   2. `localStorage aurum.ws` (migrating the legacy key `aurum.workspace` once);
 *   3. the first workspace with `kind === 'personal' && !sample && !hidden`
 *      (the server orders personal-first);
 *   4. the first non-sample workspace (samples = `profile.demo` or `profile.synthetic`);
 *   5. nothing — `wsOrNull` stays null, `error` says why, and the Shell shows `<Welcome>`.
 *
 * `ws` starts null and NO request fires until it is resolved (there is no fallback id any
 * more — the old `demo-mx` default double-fetched every screen and leaked demo data into the
 * person's own workspace). `refresh()` re-reads the list and keeps the current id; it never
 * re-applies `?ws=`.
 *
 * Typing note: `ws` is typed `string` (`''` while unresolved) because many consumers take it
 * as a string; `wsOrNull` carries the real state.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { listWorkspaces } from './api';
import { readQuery, writeQuery } from './query';
import type { Workspace } from './types';

/** localStorage registry (design-system.md): the chosen workspace id. */
export const WS_STORAGE_KEY = 'aurum.ws';
const LEGACY_STORAGE_KEY = 'aurum.workspace';
/** Same rule as the server (`WS_ID_RE` in aurum/core/config.py). */
export const WS_ID_RE = /^[a-z0-9][a-z0-9-]{1,40}$/;

export interface WorkspaceValue {
  /** The resolved id, or `''` while unresolved / when there is none (see the typing note). */
  ws: string;
  /** The real state: null until resolved. `useResource` waits on this. */
  wsOrNull: string | null;
  /** True once the resolution ran (even when it found nothing). */
  resolved: boolean;
  setWs: (id: string) => void;
  workspaces: Workspace[];
  current: Workspace | null;
  loading: boolean;
  /** Message key (`ws.none` / `ws.resolve_failed`) when nothing could be picked. */
  error: 'ws.none' | 'ws.resolve_failed' | null;
  /**
   * Re-read the workspace list (Ajustes saves `ui_mode`/`modules` and the shell reads them).
   * Keeps the current id; never re-applies `?ws=`.
   */
  refresh: () => void;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

/* ------------------------------------------------------------- storage ---- */

export function readStoredWs(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(WS_STORAGE_KEY);
    if (v) return v;
    const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (legacy) {
      window.localStorage.setItem(WS_STORAGE_KEY, legacy);
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
      return legacy;
    }
  } catch {
    /* storage blocked */
  }
  return null;
}

export function storeWs(id: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(WS_STORAGE_KEY, id);
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Read `?ws=` once: validated against the id rule, persisted, and stripped from the URL so a
 * reload or a refresh() never re-applies it. Returns the id, or null when absent/invalid.
 */
export function takeQueryWs(): string | null {
  const raw = readQuery('ws');
  if (raw === null) return null;
  writeQuery('ws', null);
  if (!WS_ID_RE.test(raw)) return null;
  storeWs(raw);
  return raw;
}

/* -------------------------------------------------------------- picking --- */

/**
 * A sample workspace: the personal demos (`profile.demo`) and the business fixture `demo-biz`,
 * which ships `profile.synthetic` instead. Neither is ever picked on its own — a first run with
 * only samples on disk shows the Welcome screen, not a tax demo.
 */
export const isSampleWorkspace = (w: Workspace) => w.profile?.demo === true || w.profile?.synthetic === true;
const isDemo = isSampleWorkspace;

/**
 * The workspace pick, pure so the four branches are unit-tested: the wanted id when listed,
 * else the first personal non-sample non-hidden, else the first non-sample, else null (→ Welcome).
 */
export function pickWorkspace(list: Workspace[], wanted: string | null): Workspace | null {
  if (wanted) {
    const hit = list.find((w) => w.id === wanted);
    if (hit) return hit;
  }
  return (
    list.find((w) => w.kind === 'personal' && !isDemo(w) && !w.hidden) ??
    list.find((w) => !isDemo(w) && !w.hidden) ??
    list.find((w) => !isDemo(w)) ??
    null
  );
}

/* ------------------------------------------------------------- provider --- */

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [ws, setWsState] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolved, setResolved] = useState(false);
  const [error, setError] = useState<WorkspaceValue['error']>(null);
  const [nonce, setNonce] = useState(0);
  // The current id as the effect sees it, so a refresh keeps it without re-running on change.
  const wsRef = useRef<string | null>(null);
  wsRef.current = ws;
  const queryTaken = useRef(false);

  useEffect(() => {
    let alive = true;
    // `?ws=` is read exactly once, on the first run, and never again on refresh().
    let wanted: string | null;
    if (!queryTaken.current) {
      queryTaken.current = true;
      wanted = takeQueryWs() ?? readStoredWs();
    } else {
      wanted = wsRef.current ?? readStoredWs();
    }
    setLoading(true);
    listWorkspaces()
      .then((list) => {
        if (!alive) return;
        setWorkspaces(list);
        const pick = pickWorkspace(list, wanted);
        if (pick) {
          setWsState(pick.id);
          storeWs(pick.id);
          setError(null);
        } else {
          setWsState(null);
          setError('ws.none');
        }
      })
      .catch(() => {
        if (!alive) return;
        // A dead API must not blank the shell: keep whatever was resolved (nothing on the
        // first run — no request may fire against a guessed id).
        setError('ws.resolve_failed');
      })
      .finally(() => {
        if (!alive) return;
        setLoading(false);
        setResolved(true);
      });
    return () => {
      alive = false;
    };
  }, [nonce]);

  const setWs = useCallback((id: string) => {
    setWsState(id);
    storeWs(id);
  }, []);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const value = useMemo<WorkspaceValue>(
    () => ({
      ws: ws ?? '',
      wsOrNull: ws,
      resolved,
      setWs,
      workspaces,
      current: workspaces.find((w) => w.id === ws) ?? null,
      loading,
      error,
      refresh,
    }),
    [ws, resolved, setWs, workspaces, loading, error, refresh],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used inside <WorkspaceProvider>');
  return ctx;
}

/** The context when present, null outside the provider (hooks that must not throw). */
export function useMaybeWorkspace(): WorkspaceValue | null {
  return useContext(WorkspaceContext);
}

/**
 * Renders `children` only once a workspace id is resolved; `fallback` (the Shell's skeleton
 * or an error box) otherwise. Inside the gate `useWorkspace().ws` is guaranteed non-empty.
 */
export function WorkspaceGate({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { wsOrNull, resolved } = useWorkspace();
  if (!resolved || wsOrNull === null) return <>{fallback}</>;
  return <>{children}</>;
}

/**
 * True when the current workspace is in `advanced` mode. A workspace saved
 * before `ui_mode` existed has none, and while the list is still loading there is no `current`
 * at all — both read as simple, the same default the Shell applies.
 */
export function useAdvanced(): boolean {
  const { current } = useWorkspace();
  return current?.ui_mode === 'advanced';
}

/**
 * True when one advanced module is visible: either the whole workspace is advanced or that
 * single module was switched on in Ajustes. `modules` itself is optional/nullable on the
 * workspace, so the key set is named through the non-null type (it equals `ModuleKey`).
 */
export function useModule(name: keyof NonNullable<Workspace['modules']>): boolean {
  const { current } = useWorkspace();
  const advanced = current?.ui_mode === 'advanced';
  return advanced || current?.modules?.[name] === true;
}
