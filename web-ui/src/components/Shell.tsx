'use client';

/**
 * App shell.
 *
 * ≥960px: brand + topbar across the top, a left rail with icon + label for the everyday
 * screens (Inicio · Movimientos · Pagos e ingresos fijos · Presupuesto · Metas · Cuentas ·
 * Categorías · Ajustes — everyday order: the jobs a person does most come first) and, last,
 * **Avanzado**: a plain link to `/avanzado/` (every advanced screen explained in one line) in
 * simple mode, or — when the workspace is advanced or a module is on — a collapsed `<details>`
 * (persisted in `aurum.advanced_open`) whose first link is that same page. Nothing deleted, no
 * route changed; the list itself lives in `lib/advanced.ts`.
 *
 * <960px: no rail; a fixed bottom tab bar Inicio · Movimientos · [+] · Cuentas · Más, where
 * the FAB opens "+ Agregar" and Más is a Sheet with the rest of the rail, language and theme.
 *
 * Topbar: the workspace name as text (a `<select>` with demos grouped only when there is a
 * real choice), spacer, **+ Agregar** — the only primary control — and a ⋯ menu Sheet holding
 * Captura rápida (advanced only), Idioma and Tema. The inbox badge polls only in advanced mode.
 *
 * Keyboard: `n` opens + Agregar (Gasto), `/` opens Captura rápida in advanced mode, Esc closes
 * whatever is open; nothing fires while typing or while a dialog is open. The skip link is the
 * first focusable element and focus moves to `<main>` after rail navigation. The Shell renders
 * the app's one `<title>` ('<screen> · Aurum'): the active nav item unless a page claims it
 * with `usePageTitle`.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { focusMain, pageTitle, useClaimedTitle, useShortcut } from '@/lib/a11y';
import { listInbox, MOCK_ENABLED } from '@/lib/api';
import { useHealth } from '@/lib/health';
import { ADVANCED_ITEMS } from '@/lib/advanced';
import { useI18n, type MsgKey } from '@/lib/i18n';
import { isSampleWorkspace, useWorkspace } from '@/lib/workspace';
import type { Lang } from '@/lib/types';
import type { ModuleKey } from '@/lib/types-personal';
import { AddEntryButton, AddEntryProvider, useAddEntry } from './AddEntry';
import { QuickAddModal } from './QuickAdd';
import { SkipLink } from './SkipLink';
import { IconButton } from './ui/Button';
import { Sheet } from './ui/Dialog';
import { ThemeToggle } from './ui/Display';
import { ErrorBox } from './ui/Feedback';
import { Icon, ICON_NAMES, type IconName } from './ui/Icon';
import { Welcome } from './Welcome';

interface NavItem {
  href: string;
  key: MsgKey;
  /** An `Icon` name for the everyday rail; a text glyph for the advanced group. */
  icon: IconName | string;
  /** Only for a business workspace — the screen reads `/api/business/...`. */
  businessOnly?: boolean;
  /** Shown in the Avanzado group when this module's flag is on, even in simple mode. */
  module?: ModuleKey;
}

/** The everyday rail: what a person uses to run their own money. */
const NAV_HOME: NavItem = { href: '/', key: 'nav.home', icon: 'home' };
const NAV_MOVIMIENTOS: NavItem = { href: '/movimientos', key: 'nav.movimientos', icon: 'list' };
const NAV_MONEY: NavItem = { href: '/money', key: 'nav.money', icon: 'calendar' };
const NAV_PRESUPUESTO: NavItem = { href: '/presupuesto/', key: 'nav.presupuesto', icon: 'target' };
const NAV_METAS: NavItem = { href: '/metas/', key: 'nav.metas', icon: 'flag' };
const NAV_CUENTAS: NavItem = { href: '/cuentas', key: 'nav.cuentas', icon: 'bank' };
const NAV_CATEGORIAS: NavItem = { href: '/categorias/', key: 'nav.categorias', icon: 'grid' };
const NAV_SETTINGS: NavItem = { href: '/settings', key: 'nav.settings', icon: 'settings' };
/** Last in the menu for everyone: the page that lists every advanced screen. */
const NAV_AVANZADO: NavItem = { href: '/avanzado/', key: 'nav.advanced', icon: 'layers' };

const PRIMARY: NavItem[] = [
  NAV_HOME,
  NAV_MOVIMIENTOS,
  NAV_MONEY,
  NAV_PRESUPUESTO,
  NAV_METAS,
  NAV_CUENTAS,
  NAV_CATEGORIAS,
  NAV_SETTINGS,
];

/** The bottom tab bar: four destinations around the FAB. */
const TABBAR: NavItem[] = [NAV_HOME, NAV_MOVIMIENTOS, NAV_CUENTAS];
/** What the "Más" sheet lists first. */
const MORE: NavItem[] = [NAV_MONEY, NAV_PRESUPUESTO, NAV_METAS, NAV_CATEGORIAS, NAV_SETTINGS];

/** Everything re-homed under Avanzado. Same routes, same screens, one click further away. */
const ADVANCED: NavItem[] = ADVANCED_ITEMS;
/** Inside the Avanzado group the page link reads "Todo lo avanzado". */
const NAV_AVANZADO_ALL: NavItem = { ...NAV_AVANZADO, key: 'adv.hub.all', icon: 'more' };

const ADVANCED_OPEN_KEY = 'aurum.advanced_open';

const pathOf = (href: string) => href.replace(/\/$/, '') || '/';

function isActive(n: NavItem, pathname: string): boolean {
  const p = pathOf(n.href);
  if (p === '/') return pathname === '/';
  return pathname === p || pathname.startsWith(`${p}/`);
}

function NavIcon({ icon }: { icon: IconName | string }) {
  if ((ICON_NAMES as string[]).includes(icon)) return <Icon name={icon as IconName} size={18} />;
  return (
    <span className="rail-icon" aria-hidden="true">
      {icon}
    </span>
  );
}

const isDemo = isSampleWorkspace;

/* ------------------------------------------------------------------- rail */

function Rail({
  inboxCount,
  advancedOpen,
  onAdvancedToggle,
  visibleAdvanced,
  onNavigate,
}: {
  inboxCount: number | null;
  advancedOpen: boolean;
  onAdvancedToggle: (open: boolean) => void;
  visibleAdvanced: NavItem[];
  onNavigate: () => void;
}) {
  const { t } = useI18n();
  const pathname = usePathname();

  const renderLink = (n: NavItem) => (
    <Link key={n.href} href={n.href} aria-current={isActive(n, pathname) ? 'page' : undefined} onClick={onNavigate}>
      <NavIcon icon={n.icon} />
      {t(n.key)}
      {n.href === '/inbox' && inboxCount ? <span className="rail-count">{inboxCount}</span> : null}
    </Link>
  );

  return (
    <nav className="rail" aria-label={t('nav.rail')}>
      {PRIMARY.map(renderLink)}

      {visibleAdvanced.length > 0 ? (
        <details className="rail-group" open={advancedOpen} onToggle={(e) => onAdvancedToggle(e.currentTarget.open)}>
          <summary>
            <NavIcon icon={NAV_AVANZADO.icon} />
            {t('nav.advanced')}
          </summary>
          {renderLink(NAV_AVANZADO_ALL)}
          {visibleAdvanced.map(renderLink)}
        </details>
      ) : (
        // Same separator as the group, so Avanzado reads as "the end of the menu".
        <div className="rail-group">{renderLink(NAV_AVANZADO)}</div>
      )}
    </nav>
  );
}

/* ----------------------------------------------------------------- chrome */

/**
 * Everything that needs `useAddEntry()` lives here, as a child of `AddEntryProvider`: the FAB,
 * the `n` shortcut and the Más/⋯ sheets.
 */
function ShellChrome({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const { ws, wsOrNull, resolved, error: wsError, refresh: refreshWorkspaces, setWs, workspaces, current } = useWorkspace();
  // First run: no personal workspace yet → Welcome in a bare shell (no rail, no + Agregar).
  const noWorkspace = resolved && wsOrNull === null;
  const { demoMode, authRequired, unauthorized } = useHealth();
  const { open: openAddEntry } = useAddEntry();
  const pathname = usePathname();

  const [quickOpen, setQuickOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [inboxCount, setInboxCount] = useState<number | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // A workspace saved before `ui_mode` existed has none; simple is the default.
  const advanced = current?.ui_mode === 'advanced';
  const modules = current?.modules ?? {};
  const visibleAdvanced = ADVANCED.filter((n) => {
    if (n.businessOnly && current?.kind !== 'business') return false;
    return advanced || (n.module ? modules[n.module] === true : false);
  });

  // Avanzado group open state: stored choice, else open when the workspace is advanced.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(ADVANCED_OPEN_KEY);
      if (stored === '1' || stored === '0') {
        setAdvancedOpen(stored === '1');
        return;
      }
    } catch {
      /* storage blocked */
    }
    setAdvancedOpen(advanced);
  }, [advanced]);
  const onAdvancedToggle = useCallback((open: boolean) => {
    setAdvancedOpen(open);
    try {
      window.localStorage.setItem(ADVANCED_OPEN_KEY, open ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, []);

  // The inbox badge is an advanced-mode thing; simple mode never calls /ingest.
  const refreshInbox = useCallback(() => {
    if (!ws || !advanced) {
      setInboxCount(null);
      return;
    }
    listInbox(ws, 'pending')
      .then((r) => setInboxCount(r.length))
      .catch(() => setInboxCount(null));
  }, [ws, advanced]);
  useEffect(() => {
    refreshInbox();
  }, [refreshInbox]);

  // Shortcuts: plain keys, never while typing or behind a dialog.
  useShortcut('n', () => openAddEntry('expense'), { when: !noWorkspace });
  useShortcut('/', (e) => {
    e.preventDefault();
    setQuickOpen(true);
  }, { when: advanced });

  // The one <title> in the app (React 19 hoists it into <head>): a page's usePageTitle claim,
  // else the active nav item. Rendered, not written to document.title, so Next's metadata
  // commit cannot overwrite it.
  const claimed = useClaimedTitle();
  const navItem = [...PRIMARY, NAV_AVANZADO, ...ADVANCED].find((n) => isActive(n, pathname));
  const title = pageTitle(claimed ?? (navItem ? t(navItem.key) : null));

  // Focus moves to <main> after a rail/tab-bar navigation, not on every route change.
  const navigated = useRef(false);
  const onNavigate = useCallback(() => {
    navigated.current = true;
    setMoreOpen(false);
  }, []);
  useEffect(() => {
    if (!navigated.current) return;
    navigated.current = false;
    focusMain();
  }, [pathname]);

  // Workspace switcher: only when there is a real choice.
  const nonDemo = workspaces.filter((w) => !isDemo(w));
  const demos = workspaces.filter(isDemo);
  const showSwitcher = nonDemo.length > 1 || (current ? isDemo(current) : false);

  const langGroup = (
    <div className="row small" role="group" aria-label={t('header.language')}>
      {(['es', 'en'] as Lang[]).map((l) => (
        <button key={l} type="button" className="ui-chip" onClick={() => setLang(l)} aria-pressed={lang === l}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );

  const sheetLink = (n: NavItem) => (
    <Link key={n.href} href={n.href} aria-current={isActive(n, pathname) ? 'page' : undefined} onClick={onNavigate}>
      <NavIcon icon={n.icon} />
      {t(n.key)}
    </Link>
  );

  return (
    <div id="app-root">
      <title>{title}</title>
      <SkipLink />
      {MOCK_ENABLED && <div className="mock-strip">{t('common.mock')}</div>}
      {demoMode && (
        <div className="mock-strip demo" role="status">
          {t('common.demo_banner')}
        </div>
      )}
      {(unauthorized || authRequired) && (
        <div className="auth-banner" role="alert">
          {t('auth.banner')} <Link href="/settings/">{t('auth.cta')}</Link>
        </div>
      )}

      <div className={noWorkspace ? 'shell bare' : 'shell'}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            Au
          </span>
          <span className="brand-name">{t('app.name')}</span>
        </div>

        <header className="topbar">
          {noWorkspace ? null : showSwitcher ? (
            <label className="row small">
              <span className="sr-only">{t('header.workspace')}</span>
              <select className="ui-select" value={ws ?? ''} onChange={(e) => setWs(e.target.value)} aria-label={t('header.workspace')}>
                {workspaces.length === 0 && <option value={ws ?? ''}>{ws}</option>}
                {nonDemo.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
                {demos.length > 0 && (
                  <optgroup label={t('header.demos')}>
                    {demos.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>
          ) : (
            <span className="ws-name" title={t('header.workspace')}>
              {current?.name ?? ws ?? ''}
            </span>
          )}

          <div className="spacer" />

          {/* Manual first: the only primary control in the chrome. */}
          {!noWorkspace && <AddEntryButton />}
          <IconButton icon="more" ariaLabel={t('header.more')} bordered onClick={() => setMenuOpen(true)} />
        </header>

        {!noWorkspace && (
          <Rail
            inboxCount={inboxCount}
            advancedOpen={advancedOpen}
            onAdvancedToggle={onAdvancedToggle}
            visibleAdvanced={visibleAdvanced}
            onNavigate={onNavigate}
          />
        )}

        <main id="main" tabIndex={-1} aria-label={t('a11y.main')}>
          {!noWorkspace ? (
            children
          ) : wsError === 'ws.resolve_failed' ? (
            <ErrorBox error={t('ws.resolve_failed')} onRetry={refreshWorkspaces} />
          ) : (
            <Welcome />
          )}
        </main>
      </div>

      {/* Bottom tab bar (<960px, CSS). */}
      {!noWorkspace && (
        <nav className="tabbar" aria-label={t('nav.rail')}>
          {TABBAR.slice(0, 2).map((n) => (
            <Link key={n.href} href={n.href} aria-current={isActive(n, pathname) ? 'page' : undefined} onClick={onNavigate}>
              <NavIcon icon={n.icon} />
              {t(n.key)}
            </Link>
          ))}
          <span className="fab-slot">
            <button type="button" className="fab" aria-label={t('a11y.add_entry')} onClick={() => openAddEntry('expense')}>
              <Icon name="plus" size={24} />
            </button>
          </span>
          {TABBAR.slice(2).map((n) => (
            <Link key={n.href} href={n.href} aria-current={isActive(n, pathname) ? 'page' : undefined} onClick={onNavigate}>
              <NavIcon icon={n.icon} />
              {t(n.key)}
            </Link>
          ))}
          <button type="button" className="tab-more" onClick={() => setMoreOpen(true)} aria-haspopup="dialog" aria-expanded={moreOpen}>
            <Icon name="more" size={18} />
            {t('header.more')}
          </button>
        </nav>
      )}

      {/* "Más" sheet: the rest of the rail + language + theme. */}
      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t('header.more')}>
        <nav className="ui-sheet-menu" aria-label={t('nav.rail')}>
          {MORE.map(sheetLink)}
          {visibleAdvanced.length > 0 ? (
            <>
              <span className="ui-sheet-group">{t('nav.advanced')}</span>
              {sheetLink(NAV_AVANZADO_ALL)}
              {visibleAdvanced.map(sheetLink)}
            </>
          ) : (
            sheetLink(NAV_AVANZADO)
          )}
          <span className="ui-sheet-group">{t('header.language')}</span>
          <div className="ui-sheet-row">{langGroup}</div>
          <span className="ui-sheet-group">{t('header.theme')}</span>
          <div className="ui-sheet-row">
            <ThemeToggle />
          </div>
        </nav>
      </Sheet>

      {/* ⋯ menu: Captura rápida (advanced only), Idioma, Tema. */}
      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} title={t('header.more')}>
        <div className="ui-sheet-menu">
          {advanced && (
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                // After the sheet closes, so the quick-add dialog is not stacked under it.
                window.setTimeout(() => setQuickOpen(true), 0);
              }}
            >
              <Icon name="search" size={18} />
              {t('header.quickadd')} <span className="kbd">/</span>
            </button>
          )}
          <span className="ui-sheet-group">{t('header.language')}</span>
          <div className="ui-sheet-row">{langGroup}</div>
          <span className="ui-sheet-group">{t('header.theme')}</span>
          <div className="ui-sheet-row">
            <ThemeToggle />
          </div>
        </div>
      </Sheet>

      <QuickAddModal
        open={quickOpen}
        onClose={(accepted) => {
          setQuickOpen(false);
          if (accepted) refreshInbox();
        }}
      />
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  return (
    <AddEntryProvider>
      <ShellChrome>{children}</ShellChrome>
    </AddEntryProvider>
  );
}
