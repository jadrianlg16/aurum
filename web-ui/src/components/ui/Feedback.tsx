'use client';

/**
 * Loading / empty / error primitives.
 *
 * - `Skeleton` keeps the layout in place while the first load runs: `role="status"`,
 *   `aria-busy`, an sr label `Cargando {what}`; the shimmer is CSS and stops under
 *   `prefers-reduced-motion`. Reloads never swap content for a skeleton (stale-while-refresh).
 * - `EmptyState` is a labelled `<section>`: one sentence of what belongs here, one of why, a
 *   primary `Button` (the manual path) and an optional secondary text link marked `(atajo)`.
 * - `ErrorBox` is a `role="alert"` with the message from `ApiError.message` (or a string), a
 *   Reintentar button, and — on 401 — a link to Ajustes.
 */
import Link from 'next/link';
import { useId, type ReactNode } from 'react';
import { useI18n } from '@/lib/i18n';
import { Button, type ButtonProps } from './Button';
import { Icon, type IconName } from './Icon';

export type SkeletonVariant = 'text' | 'stat' | 'table' | 'card' | 'list';

export function Skeleton({
  variant = 'text',
  rows = 3,
  what,
  className,
}: {
  variant?: SkeletonVariant;
  rows?: number;
  /** Fills `Cargando {what}`; defaults to "contenido". */
  what?: string;
  className?: string;
}) {
  const { t } = useI18n();
  const label = t('common.loading.sr', { what: what ?? t('common.content') });
  const bars: ReactNode[] = [];
  const n = Math.max(1, rows);
  if (variant === 'stat') {
    bars.push(<span key="l" className="ui-skel-bar w60" />, <span key="v" className="ui-skel-bar stat" />);
  } else if (variant === 'card') {
    for (let i = 0; i < n; i += 1) bars.push(<span key={i} className="ui-skel-bar card" />);
  } else if (variant === 'table' || variant === 'list') {
    for (let i = 0; i < n; i += 1) bars.push(<span key={i} className="ui-skel-bar row" />);
  } else {
    for (let i = 0; i < n; i += 1) {
      bars.push(<span key={i} className={`ui-skel-bar${i % 3 === 2 ? ' w60' : i % 3 === 1 ? ' w80' : ''}`} />);
    }
  }
  return (
    <div className={['ui-skel', className].filter(Boolean).join(' ')} role="status" aria-busy="true" aria-label={label}>
      {bars}
    </div>
  );
}

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  body?: ReactNode;
  /** The manual, primary path. */
  primary?: { label: string; onClick?: () => void; href?: string; variant?: ButtonProps['variant'] };
  /** The shortcut, rendered as a text link suffixed "(atajo)". */
  secondary?: { label: string; onClick?: () => void; href?: string };
  compact?: boolean;
  className?: string;
}

export function EmptyState({ icon, title, body, primary, secondary, compact, className }: EmptyStateProps) {
  const { t } = useI18n();
  const id = useId();
  const Heading = compact ? 'h3' : 'h2';
  return (
    <section className={['ui-empty', compact ? 'compact' : '', className].filter(Boolean).join(' ')} aria-labelledby={id}>
      {icon && !compact && (
        <span className="ui-empty-icon">
          <Icon name={icon} size={28} />
        </span>
      )}
      <Heading id={id}>{title}</Heading>
      {body && <p>{body}</p>}
      {(primary || secondary) && (
        <div className="ui-empty-actions">
          {primary && (
            <Button variant={primary.variant ?? 'primary'} onClick={primary.onClick} href={primary.href}>
              {primary.label}
            </Button>
          )}
          {secondary &&
            (secondary.href ? (
              <Link className="ui-empty-secondary" href={secondary.href}>
                {secondary.label} ({t('common.shortcut')})
              </Link>
            ) : (
              <button type="button" className="ui-empty-secondary" onClick={secondary.onClick}>
                {secondary.label} ({t('common.shortcut')})
              </button>
            ))}
        </div>
      )}
    </section>
  );
}

/** Pull a human message and a status out of whatever was thrown. */
export function errorMessage(error: unknown): { message: string; status: number | null } {
  if (typeof error === 'string') return { message: error, status: null };
  if (error && typeof error === 'object') {
    const e = error as { message?: unknown; status?: unknown; detail?: unknown };
    const status = typeof e.status === 'number' ? e.status : null;
    if (typeof e.message === 'string' && e.message) return { message: e.message, status };
    if (typeof e.detail === 'string' && e.detail) return { message: e.detail, status };
  }
  return { message: '', status: null };
}

export function ErrorBox({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const { t } = useI18n();
  const { message, status } = errorMessage(error);
  return (
    <div className={['ui-errorbox', className].filter(Boolean).join(' ')} role="alert">
      <p>
        <strong>{t('common.error')}</strong>
        {message ? ` · ${message}` : ''}
      </p>
      {status === 401 && (
        <p>
          {t('auth.banner')} <Link href="/settings/">{t('auth.cta')}</Link>
        </p>
      )}
      {onRetry && (
        <div className="row">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        </div>
      )}
    </div>
  );
}
