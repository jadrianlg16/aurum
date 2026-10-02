import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Shell } from '@/components/Shell';
import { ToastProvider } from '@/components/ui/Toast';
import { HealthProvider } from '@/lib/health';
import { I18nProvider } from '@/lib/i18n';
import { ThemeProvider } from '@/lib/theme';
import { WorkspaceProvider } from '@/lib/workspace';

/**
 * Pre-hydration theme script. Inlined here (not imported from lib/theme.tsx,
 * a client module whose non-component exports are not readable from a server component).
 * Same key as `THEME_STORAGE_KEY` in lib/theme.tsx; 124 bytes.
 */
const THEME_BOOT_SCRIPT =
  "try{var t=localStorage.getItem('aurum.theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}";

export const metadata: Metadata = {
  // No `title` here on purpose: the Shell renders the one <title> ('<screen> · Aurum') and
  // React 19 hoists it, so per-page titles never fight Next's metadata commit.
  description: 'Tus cuentas, gastos e ingresos, a mano y explicados.',
  applicationName: 'Aurum',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon.ico', sizes: '32x32' },
    ],
    apple: '/apple-touch-icon.png',
  },
  appleWebApp: { capable: true, title: 'Aurum', statusBarStyle: 'default' },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  // The `--paper` values from globals.css; lib/theme.tsx rewrites the meta when the user picks
  // a theme explicitly.
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f6f3' },
    { media: '(prefers-color-scheme: dark)', color: '#141312' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // lang="es" is the default; the I18n provider rewrites it when the user
  // toggles to English, so the attribute always matches what is on screen.
  //
  // The inline script applies the stored theme before the first paint (no flash of the wrong
  // palette). It is 124 bytes, wrapped in try/catch, and relies on the CSP's existing
  // 'unsafe-inline' for scripts — if the CSP is ever tightened it must be hashed
  // (docs/modules/design-system.md "Theme").
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <I18nProvider>
            <WorkspaceProvider>
              <HealthProvider>
                <ToastProvider>
                  <Shell>{children}</Shell>
                </ToastProvider>
              </HealthProvider>
            </WorkspaceProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
