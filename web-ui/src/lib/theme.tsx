'use client';

/**
 * Theme: `system` (follow the OS), `light` or `dark`.
 *
 * The palette lives in globals.css three times — light on bare `:root`, dark under the
 * `prefers-color-scheme` media query (unless `data-theme='light'` forces light) and dark again
 * under `:root[data-theme='dark']`. This provider only flips that attribute and keeps the
 * `<meta name="theme-color">` in step, so the browser chrome matches `--paper`.
 *
 * The first paint is handled by the tiny inline script in `app/layout.tsx`, which reads the
 * same localStorage key before React runs; this provider takes over after hydration. The
 * stored value is applied in an effect (never in the initial state) so server and client
 * render the same tree.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Theme = 'system' | 'light' | 'dark';

/** localStorage key — listed in the registry in docs/modules/design-system.md. */
export const THEME_STORAGE_KEY = 'aurum.theme';

/** `--paper` per effective theme; kept in one place so the manifest and the meta agree. */
const PAPER: Record<'light' | 'dark', string> = { light: '#f7f6f3', dark: '#141312' };

interface ThemeValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** What is actually on screen once `system` is resolved. */
  effective: 'light' | 'dark';
}

const ThemeContext = createContext<ThemeValue>({
  theme: 'system',
  setTheme: () => {},
  effective: 'light',
});

function isTheme(v: unknown): v is Theme {
  return v === 'system' || v === 'light' || v === 'dark';
}

function readStored(): Theme {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(v) ? v : 'system';
  } catch {
    return 'system';
  }
}

function systemPrefersDark(): boolean {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch {
    return false;
  }
}

/** Sets or removes `data-theme` and rewrites the theme-color meta. Safe to call repeatedly. */
export function applyTheme(theme: Theme): 'light' | 'dark' {
  const root = document.documentElement;
  if (theme === 'system') delete root.dataset.theme;
  else root.dataset.theme = theme;
  const effective = theme === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : theme;
  let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]:not([media])');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.appendChild(meta);
  }
  meta.content = PAPER[effective];
  return effective;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system');
  const [effective, setEffective] = useState<'light' | 'dark'>('light');

  // Pick up the stored choice after mount (the inline script already painted it).
  useEffect(() => {
    const stored = readStored();
    setThemeState(stored);
    setEffective(applyTheme(stored));
  }, []);

  // Follow the OS while on `system`.
  useEffect(() => {
    if (theme !== 'system') return undefined;
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia('(prefers-color-scheme: dark)');
    } catch {
      return undefined;
    }
    const onChange = () => setEffective(applyTheme('system'));
    mq.addEventListener('change', onChange);
    return () => mq?.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    setEffective(applyTheme(t));
    try {
      if (t === 'system') window.localStorage.removeItem(THEME_STORAGE_KEY);
      else window.localStorage.setItem(THEME_STORAGE_KEY, t);
    } catch {
      /* storage blocked — the attribute still applied */
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme, effective }), [theme, setTheme, effective]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}

/*
 * The pre-hydration script lives inline in `app/layout.tsx` (a server component cannot read a
 * string export from this client module). It reads THEME_STORAGE_KEY and sets `data-theme`
 * before the first paint; keep the two in sync.
 */
