'use client';

/**
 * Route error boundary: sits inside the layout providers, so `useI18n` works here.
 * Reintentar calls Next's `reset()` to re-render the failed segment.
 */
import { useEffect } from 'react';
import { usePageTitle } from '@/lib/a11y';
import { useI18n } from '@/lib/i18n';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  usePageTitle(t('error.title'));
  useEffect(() => {
    // The message only — never request bodies, never PII (no PII in logs, docs/ARCHITECTURE.md).
    console.error('route error', error?.message, error?.digest);
  }, [error]);
  return (
    <div className="ui-errorpage" role="alert">
      <Icon name="alert" size={32} />
      <h1>{t('error.title')}</h1>
      <p className="muted">{t('error.body')}</p>
      <div className="row">
        <Button variant="primary" onClick={reset}>
          {t('common.retry')}
        </Button>
        <Button href="/">{t('notfound.home')}</Button>
      </div>
    </div>
  );
}
