'use client';

/**
 * Below 768px the filters live behind a "Filtros" button that opens a bottom `Sheet`
 * (ui/Dialog) with the account and category pickers and the kind tabs; the search box stays
 * on the page. The button shows how many filters are active.
 */
import { useState } from 'react';
import { useI18n } from '@/lib/i18n';
import { Button, Sheet } from '@/components/ui';
import { activeFilterCount, KindTabs, PickerFields, SearchField, type FilterProps } from './FilterBar';
import styles from './movimientos.module.css';

export function FilterSheet(props: FilterProps) {
  const { t } = useI18n();
  const { value, onChange, onClear } = props;
  const [open, setOpen] = useState(false);
  const active = activeFilterCount(value);
  const label = active > 0 ? `${t('txn.filters')} (${active})` : t('txn.filters');
  return (
    <div className={styles.toolbar}>
      <SearchField value={value.q} onChange={(q) => onChange({ q })} className={styles.toolbarSearch} />
      <div className={styles.toolbarEnd}>
        <Button variant="secondary" icon="settings" onClick={() => setOpen(true)} aria-expanded={open}>
          {label}
        </Button>
        {(active > 0 || value.q) && (
          <Button variant="ghost" onClick={onClear}>
            {t('txn.filters.clear')}
          </Button>
        )}
      </div>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t('txn.filters')}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                onClear();
                setOpen(false);
              }}
            >
              {t('txn.filters.clear')}
            </Button>
            <span className="spacer" />
            <Button variant="primary" onClick={() => setOpen(false)}>
              {t('common.close')}
            </Button>
          </>
        }
      >
        <div className={styles.sheetBody}>
          <PickerFields {...props} />
          <KindTabs value={value.kind} onChange={(kind) => onChange({ kind })} />
        </div>
      </Sheet>
    </div>
  );
}
