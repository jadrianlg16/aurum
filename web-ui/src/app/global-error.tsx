'use client';

/**
 * Last-resort boundary: renders when the root layout itself throws, so it sits outside
 * every provider — no `useI18n`, no theme, its own `<html><body>`. Bilingual literals on
 * purpose. globals.css is not guaranteed to be loaded here, hence the minimal inline styles.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="es">
      <body style={{ fontFamily: 'system-ui, sans-serif', background: '#f7f6f3', color: '#1c1a17', margin: 0 }}>
        <main
          role="alert"
          style={{ maxWidth: '48ch', margin: '48px auto', padding: '0 16px', textAlign: 'center', display: 'grid', gap: 12 }}
        >
          <h1 style={{ fontSize: 22, margin: 0 }}>Algo salió mal · Something went wrong</h1>
          <p style={{ color: '#6b665e', margin: 0 }}>
            No se pudo mostrar la aplicación. Vuelve a intentarlo o recarga la página.
            <br />
            The app could not be shown. Try again or reload the page.
          </p>
          {error?.digest && (
            <p style={{ color: '#6b665e', fontSize: 12, margin: 0 }}>
              ref: <code>{error.digest}</code>
            </p>
          )}
          <p style={{ margin: 0 }}>
            <button
              type="button"
              onClick={reset}
              style={{
                background: '#b8860b',
                color: '#1c1a17',
                border: 0,
                borderRadius: 6,
                padding: '10px 16px',
                minHeight: 44,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Reintentar · Retry
            </button>
          </p>
        </main>
      </body>
    </html>
  );
}
