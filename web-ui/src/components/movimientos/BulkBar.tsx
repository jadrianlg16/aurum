'use client';

/**
 * Sticky bar shown while rows are selected: "{n} seleccionados", a category picker and
 * "Poner categoría" (one `PUT /entries/{id}` with exactly `{label_id}` per row — the page
 * does the sending), plus "Quitar selección".
 */
import { useI18n } from '@/lib/i18n';
import { Button, CategoryPicker, Field } from '@/components/ui';
import styles from './movimientos.module.css';

export function BulkBar({
  ws,
  count,
  labelId,
  onLabel,
  onApply,
  onClear,
  busy,
  version,
}: {
  ws: string;
  count: number;
  labelId: string;
  onLabel: (id: string) => void;
  onApply: () => void;
  onClear: () => void;
  busy: boolean;
  version: number;
}) {
  const { t, tn } = useI18n();
  return (
    <div className={styles.bulkbar} role="region" aria-label={tn('txn.selected', count)}>
      <strong>{tn('txn.selected', count)}</strong>
      <Field label={t('txn.col.category')} className={styles.bulkField}>
        <CategoryPicker ws={ws} value={labelId} onChange={onLabel} version={version} disabled={busy} />
      </Field>
      <Button variant="primary" onClick={onApply} disabled={!labelId || busy} loading={busy}>
        {t('txn.bulk.set_category')}
      </Button>
      <Button variant="ghost" onClick={onClear} disabled={busy}>
        {t('txn.bulk.clear')}
      </Button>
    </div>
  );
}
