'use client';

/**
 * One movement as a `ResponsiveTable` row: the column set (checkbox,
 * comercio, categoría, cuenta, monto, origen), how each cell lands on the mobile card
 * (title / subtitle / value / meta) and the per-row ⋯ actions.
 *
 * No date column (the day heading already says it), the checkbox column only
 * while "Seleccionar varios" is on, and the origin column only when some row is not manual
 * or is locked (or in advanced mode) — an always-empty "Origen" was noise.
 *
 * Locked rows (`editable: false`, e.g. a payroll or invoice row) never say the server's
 * `non_editable_reason`; they show "Se capturó desde Nómina y no se puede cambiar aquí." and
 * offer Duplicar only (PUT/DELETE would answer 403). Amounts always carry their sign.
 */
import Link from 'next/link';
import type { MouseEvent, KeyboardEvent } from 'react';
import { useI18n, useMoney } from '@/lib/i18n';
import type { Entry, EntrySource } from '@/lib/types-personal';
import { Badge, Icon, Money, type Column, type RowAction } from '@/components/ui';
import styles from './movimientos.module.css';

const ORIGIN_KEY: Record<EntrySource, `txn.origin.${EntrySource}`> = {
  manual: 'txn.origin.manual',
  quickadd: 'txn.origin.quickadd',
  import: 'txn.origin.import',
  cfdi: 'txn.origin.cfdi',
  payroll: 'txn.origin.payroll',
  organizer: 'txn.origin.organizer',
};

export interface MovementRowOptions {
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  /** Adds the "Abrir en la vista avanzada" link on locked rows. */
  advanced: boolean;
  onEdit: (row: Entry) => void;
  onDuplicate: (row: Entry) => void;
  onDelete: (row: Entry) => void;
  /** Below 768px the checkbox column is hidden; selection moves into the ⋯ menu. */
  narrow: boolean;
  /** "Seleccionar varios" is on: the checkbox column is shown. */
  selecting: boolean;
  /** Some row on screen has a non-manual source or is locked (or the workspace is advanced). */
  showOrigin: boolean;
}

const stop = (e: MouseEvent | KeyboardEvent) => e.stopPropagation();

export function useMovementColumns(opts: MovementRowOptions): Column<Entry>[] {
  const { t } = useI18n();
  const { fmt } = useMoney();
  const { selected, onToggle, advanced, selecting, showOrigin } = opts;

  const columns: Column<Entry>[] = [
    {
      key: 'select',
      header: '',
      mobile: 'hidden',
      colClass: styles.colCheck,
      render: (e) => (
        // The label wraps the box (44px tap target); clicks stop here so the row does not open.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
        <label className={styles.check} onClick={stop} onKeyDown={stop}>
          <input
            type="checkbox"
            className={styles.rowCheck}
            checked={selected.has(e.id)}
            onChange={() => onToggle(e.id)}
          />
          <span className="sr-only">{t('txn.select.row', { payee: e.payee?.trim() || '—', amount: fmt(e.amount, { sign: 'always' }) })}</span>
        </label>
      ),
    },
    {
      key: 'payee',
      header: t('txn.col.payee'),
      mobile: 'title',
      colClass: styles.colPayee,
      render: (e) => (
        <>
          {e.payee?.trim() || '—'}
          {e.attachment && (
            <span className={styles.rowClip}>
              <Icon name="clip" size={14} label={t('receipt.has_photo')} />
            </span>
          )}
          {e.note && <span className={styles.rowNote}>{e.note}</span>}
        </>
      ),
    },
    {
      key: 'category',
      header: t('txn.col.category'),
      mobile: 'subtitle',
      colClass: styles.colCategory,
      render: (e) => (e.kind === 'transfer' ? t('txn.kind.transfer') : e.label_name ?? t('txn.uncategorized')),
    },
    {
      key: 'account',
      header: t('txn.col.account'),
      mobile: 'subtitle',
      colClass: styles.colAccount,
      render: (e) => (e.kind === 'transfer' && e.to_account_name ? `${e.account_name ?? '—'} → ${e.to_account_name}` : e.account_name ?? '—'),
    },
    {
      key: 'amount',
      header: t('txn.col.amount'),
      numeric: true,
      mobile: 'value',
      colClass: styles.colAmount,
      render: (e) => (
        <Money amount={e.amount} sign="always" tone={e.kind === 'transfer' ? 'neutral' : 'auto'} className={e.kind === 'transfer' ? 'muted' : undefined} />
      ),
    },
    {
      key: 'origin',
      header: t('txn.source'),
      mobile: 'meta',
      colClass: styles.colOrigin,
      render: (e) => {
        const source = e.source ?? 'manual';
        const locked = e.editable === false;
        if (source === 'manual' && !locked) return '';
        return (
          <>
            {source !== 'manual' && <Badge tone="neutral">{t(ORIGIN_KEY[source])}</Badge>}
            {locked && (
              <span className={styles.rowLocked}>
                {t('txn.locked.source', { source: t(ORIGIN_KEY[source]) })}
                {advanced && (
                  <>
                    {' '}
                    <Link href="/books/" onClick={stop}>
                      {t('txn.locked.open_adv')}
                    </Link>
                  </>
                )}
              </span>
            )}
          </>
        );
      },
    },
  ];
  return columns.filter((c) => (c.key === 'select' ? selecting : c.key === 'origin' ? showOrigin : true));
}

/** The ⋯ menu: Editar / Duplicar / Eliminar (locked rows: Duplicar only); selection on phones. */
export function useMovementActions(opts: MovementRowOptions): (row: Entry) => RowAction<Entry>[] {
  const { t } = useI18n();
  const { selected, onToggle, onEdit, onDuplicate, onDelete, narrow } = opts;
  return (row: Entry) => {
    const editable = row.editable !== false;
    const out: RowAction<Entry>[] = [];
    if (editable) out.push({ label: t('form.edit'), onClick: onEdit });
    out.push({ label: t('txn.duplicate'), onClick: onDuplicate });
    if (narrow) {
      out.push({ label: selected.has(row.id) ? t('txn.select.remove') : t('txn.select_row'), onClick: (r) => onToggle(r.id) });
    }
    if (editable) out.push({ label: t('form.delete'), onClick: onDelete, destructive: true });
    return out;
  };
}
