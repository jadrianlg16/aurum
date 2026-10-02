'use client';

/**
 * Filters for Movimientos: search (debounced by the page), account,
 * category (`kind` undefined = expense + income), kind tabs and "Quitar filtros". `FilterBar`
 * lays them out inline from 768px; `FilterSheet` (FilterSheet.tsx) puts the same controls in
 * a bottom sheet below that width, keeping only the search box on the page.
 */
import { useI18n } from '@/lib/i18n';
import type { EntryKind } from '@/lib/types-personal';
import { AccountPicker, Button, CategoryPicker, Field, Input, Tabs, type TabItem } from '@/components/ui';
import styles from './movimientos.module.css';

/** Tab ids: `all` stands for "no kind filter" (`''` on the wire). */
export type KindTab = 'all' | EntryKind;
export const kindOfTab = (tab: KindTab): EntryKind | '' => (tab === 'all' ? '' : tab);

export interface FilterState {
  q: string;
  accountId: string;
  labelId: string;
  kind: KindTab;
}

export interface FilterProps {
  ws: string;
  value: FilterState;
  onChange: (next: Partial<FilterState>) => void;
  onClear: () => void;
  /** Bump after a write so the pickers refetch. */
  version: number;
}

export function activeFilterCount(f: FilterState): number {
  return (f.accountId ? 1 : 0) + (f.labelId ? 1 : 0) + (f.kind !== 'all' ? 1 : 0);
}

export function SearchField({ value, onChange, className }: { value: string; onChange: (q: string) => void; className?: string }) {
  const { t } = useI18n();
  return (
    <Field label={t('common.search')} className={className}>
      <Input type="search" value={value} placeholder={t('txn.search')} onChange={(e) => onChange(e.target.value)} autoComplete="off" />
    </Field>
  );
}

export function KindTabs({ value, onChange, className }: { value: KindTab; onChange: (k: KindTab) => void; className?: string }) {
  const { t } = useI18n();
  const items: TabItem<KindTab>[] = [
    { id: 'all', label: t('txn.all.kinds') },
    { id: 'expense', label: t('txn.kind.expense') },
    { id: 'income', label: t('txn.kind.income') },
    { id: 'transfer', label: t('txn.kind.transfer') },
  ];
  // `kindTabs` (movimientos.module.css) lifts the primitive's 36px pills to the 44px tap target on touch/narrow screens.
  return <Tabs items={items} value={value} onChange={onChange} label={t('txn.filter.kind')} className={[styles.kindTabs, className].filter(Boolean).join(' ')} />;
}

/** The account + category pickers, shared by the bar and the sheet. */
export function PickerFields({ ws, value, onChange, version, className }: FilterProps & { className?: string }) {
  const { t } = useI18n();
  return (
    <>
      <Field label={t('txn.filter.account')} className={className}>
        <AccountPicker ws={ws} value={value.accountId} onChange={(id) => onChange({ accountId: id })} placeholder={t('txn.all')} version={version} />
      </Field>
      <Field label={t('txn.filter.category')} className={className}>
        <CategoryPicker ws={ws} value={value.labelId} onChange={(id) => onChange({ labelId: id })} version={version} placeholder={t('txn.all')} />
      </Field>
    </>
  );
}

export function FilterBar(props: FilterProps) {
  const { t } = useI18n();
  const { value, onChange, onClear } = props;
  const active = activeFilterCount(value);
  return (
    <div className={styles.toolbar}>
      <SearchField value={value.q} onChange={(q) => onChange({ q })} className={styles.toolbarSearch} />
      <PickerFields {...props} className={styles.toolbarField} />
      <KindTabs value={value.kind} onChange={(kind) => onChange({ kind })} className={styles.toolbarTabs} />
      {(active > 0 || value.q) && (
        <Button variant="ghost" onClick={onClear}>
          {t('txn.filters.clear')}
        </Button>
      )}
    </div>
  );
}
