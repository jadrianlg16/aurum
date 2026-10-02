'use client';

/**
 * 404 inside the shell. The static export emits it as `/404.html`; nginx serves it for
 * unknown paths (`error_page 404 /404.html` in nginx.conf.template).
 */
import { usePageTitle } from '@/lib/a11y';
import { useI18n } from '@/lib/i18n';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';

export default function NotFound() {
  const { t } = useI18n();
  usePageTitle(t('notfound.title'));
  return (
    <div className="ui-errorpage">
      <Icon name="alert" size={32} />
      <h1>{t('notfound.title')}</h1>
      <Button variant="primary" href="/">
        {t('notfound.home')}
      </Button>
    </div>
  );
}
