'use client';

/**
 * `MoreOptions` — the plain-language disclosure for optional fields. A form shows only what a
 * person must answer; everything with a sensible default (institution, currency, notes, the
 * exact day…) sits behind "Más opciones", closed unless `defaultOpen`.
 */
import type { ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';

export function MoreOptions({ children, defaultOpen = false, label }: { children: ReactNode; defaultOpen?: boolean; label?: string }) {
  const { t } = useI18n();
  return (
    <details className="ui-more" open={defaultOpen || undefined}>
      <summary>{label ?? t('form.more_options')}</summary>
      <div className="stack">{children}</div>
    </details>
  );
}
