'use client';

/**
 * "Ir al contenido" — the first focusable element on every page. It moves keyboard
 * focus to `<main id="main" tabIndex={-1}>` rather than only scrolling to the anchor, so the
 * next Tab lands inside the content.
 */
import { focusMain } from '@/lib/a11y';
import { useI18n } from '@/lib/i18n';

export function SkipLink() {
  const { t } = useI18n();
  return (
    <a
      className="skip"
      href="#main"
      onClick={(e) => {
        e.preventDefault();
        focusMain();
      }}
    >
      {t('a11y.skip')}
    </a>
  );
}
