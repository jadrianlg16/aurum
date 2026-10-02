'use client';

/**
 * `(verify)` chips — "never guess a rate" (docs/ARCHITECTURE.md) made visible.
 *
 * Every rule reports the constants it could not confirm against the official text
 * (`unverified_constants`). Rather than hide them, the screens list them: a figure that leans
 * on an unverified constant is an estimate, and the user should see which ones.
 */
import { useI18n } from '@/lib/i18n';

export function VerifyChip({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <span className="badge warn" title={t('tax.us.unverified_hint')}>
      {label ? `${label} ${t('common.verify')}` : t('common.verify')}
    </span>
  );
}

export function UnverifiedList({ keys }: { keys: string[] }) {
  const { t } = useI18n();
  if (keys.length === 0) return null;
  return (
    <div className="card">
      <div className="metric-label">{t('tax.us.unverified')}</div>
      <div className="row small" style={{ flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
        {keys.map((k) => (
          <VerifyChip key={k} label={k} />
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        {t('tax.us.unverified_hint')}
      </p>
    </div>
  );
}
